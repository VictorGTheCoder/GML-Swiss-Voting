"""Create an immutable municipal forecast batch before its voting date.

The historical input is an already prepared training table. Current OFS
outcomes are never read or joined into the future population. Publication
vintages and the fixed 2026 geography still limit the research candidate; a
batch captured before a vote is not a guarantee of predictive accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.common.vote_keys import ofs_keys
from scripts.integration.build_modeling_dataset import (
    DEMOGRAPHICS,
    KEYS,
    OBJECT_FIELDS,
    PARTIES,
    SOURCES,
    TYPOLOGIES,
    asof_join,
    election_wide,
    unique_keys,
)
from scripts.modeling.direction_features_v2 import add_direction_features
from scripts.modeling.experiment_control_v2 import verify_freeze
from scripts.modeling.municipal_v2 import DEFAULT_OUTPUT, digest, freeze_history, write_json
from scripts.modeling.political_features_v2 import add_political_features

DEFAULT_POLLS = ROOT / "data/external/polls/srg_gfs_polls.csv"
OUTCOME_COLUMNS = frozenset({
    "yes_share", "target_share", "target", "votes_yes", "votes_no", "yes_count",
    "no_count", "national_yes_share", "volkja", "volknein", "volkja-proz",
    "annahme", "turnout", "valid_ballots", "ballots_cast", "eligible_voters",
})
USED_SOURCES = ("swissvotes", "statpop", "elections", "typologies")


def _timestamp(value, label):
    """Use UTC instants internally, represented as timezone-naive timestamps."""
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label}: {value!r}") from error
    if pd.isna(timestamp):
        raise ValueError(f"Missing {label}")
    timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    return timestamp.tz_localize(None)


def _dates(values, label):
    dates = pd.to_datetime(values, errors="coerce", utc=True)
    if dates.isna().any():
        raise ValueError(f"Missing or invalid {label}")
    return dates.dt.tz_localize(None)


def _utc_iso(timestamp):
    return pd.Timestamp(timestamp).tz_localize("UTC").isoformat().replace("+00:00", "Z")


def _require_columns(frame, names, label):
    if not frame.columns.is_unique:
        raise ValueError(f"{label}: duplicate column names")
    missing = set(names) - set(frame.columns)
    if missing:
        raise ValueError(f"{label}: missing columns {sorted(missing)}")


def _historical_frame(training_table, as_of):
    columns = ["municipality_id", "vote_id", "vote_date", "canton", "yes_share",
               "history_mean_yes", "history_n_objects"]
    _require_columns(training_table, columns, "Training table")
    train = training_table[columns].copy()
    if train.empty:
        raise ValueError("A nonempty prepared training table is required")
    train["municipality_id"] = train.municipality_id.astype("string")
    train["vote_id"] = ofs_keys(train.vote_id)
    unique_keys(train, KEYS, "Training table")
    if train.municipality_id.str.strip().eq("").any():
        raise ValueError("Empty historical municipality identifier")
    train["vote_date"] = _dates(train.vote_date, "historical voting dates").dt.normalize()
    # Results on the cutoff day need release evidence which this input does not
    # carry. Require strictly earlier calendar dates instead of assuming it.
    if train.vote_date.max() >= as_of.normalize():
        raise ValueError("Historical results must strictly precede the as_of date")
    if train.groupby("vote_id").vote_date.nunique().gt(1).any():
        raise ValueError("One historical object has conflicting voting dates")
    for name in ("yes_share", "history_mean_yes", "history_n_objects"):
        train[name] = pd.to_numeric(train[name], errors="coerce").astype(float)
    if not (np.isfinite(train.yes_share) & train.yes_share.between(0, 1)).all():
        raise ValueError("Invalid historical target shares")
    counts = train.history_n_objects
    if not (np.isfinite(counts) & counts.ge(0) & counts.mod(1).eq(0)).all():
        raise ValueError("Invalid historical object counts")
    means = train.history_mean_yes
    if not ((np.isfinite(means) & means.between(0, 1)) | (means.isna() & counts.eq(0))).all():
        raise ValueError("Missing or invalid past mean for nonempty history")
    if train.groupby(["municipality_id", "vote_date"])[
        ["history_mean_yes", "history_n_objects"]
    ].nunique(dropna=False).gt(1).any().any():
        raise ValueError("Same-date objects must share the same strictly prior history")
    return train


def build_future_frame(training_table, sources, vote_date, as_of):
    """Build future predictors without creating or reading a future target.

    ``sources`` accepts the existing prepared source mapping. Its ``ofs``
    member, if supplied, is deliberately unused. ``sources['polls']`` is an
    optional pre-vote poll DataFrame; its adapter is imported only when needed.
    All as-of joins use ``as_of``, never the day before the future voting date.
    """
    voting_date = _timestamp(vote_date, "vote_date").normalize()
    cutoff = _timestamp(as_of, "as_of")
    if voting_date <= cutoff:
        raise ValueError("vote_date must be strictly after as_of")
    absent = set(USED_SOURCES) - set(sources)
    if absent:
        raise ValueError(f"Missing prepared sources: {sorted(absent)}")
    train = _historical_frame(training_table, cutoff)
    latest_date = train.vote_date.max()
    if voting_date <= latest_date:
        raise ValueError("vote_date must be strictly after all training dates")

    population = train.loc[train.vote_date.eq(latest_date), ["municipality_id", "canton"]].drop_duplicates()
    if population.canton.isna().any() or population.canton.astype("string").str.strip().eq("").any():
        raise ValueError("The latest historical population has missing canton metadata")
    unique_keys(population, ["municipality_id"], "Latest-date municipality population")
    population = population.sort_values("municipality_id").reset_index(drop=True)

    swiss = sources["swissvotes"]
    _require_columns(swiss, ["vote_key", "vote_date", *OBJECT_FIELDS], "Swissvotes")
    source_dates = pd.to_datetime(swiss.vote_date, errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    objects = swiss.loc[source_dates.eq(voting_date)].copy()
    if objects.empty:
        raise ValueError("No Swissvotes objects match the exact future voting date")
    objects["vote_key"] = ofs_keys(objects.vote_key)
    unique_keys(objects, ["vote_key"], "Future Swissvotes objects")
    legal_form = pd.to_numeric(objects.rechtsform, errors="coerce")
    if not legal_form.isin([1, 2, 3, 4, 5]).all():
        raise ValueError("Future objects have unknown legal forms")
    subsidiary_count = int(legal_form.eq(5).sum())
    objects = objects.loc[~legal_form.eq(5)].copy()
    if objects.empty:
        raise ValueError("No principal future object remains after excluding subsidiary questions")
    objects["vote_date"] = voting_date
    objects = objects.sort_values("vote_key").reset_index(drop=True)

    # Build only from identifier/date projections: no outcome placeholder, not
    # even a column full of NaNs, is allowed in a future feature matrix.
    identifiers = objects[["vote_key", "vote_date"]].copy()
    identifiers["vote_id"] = identifiers.vote_key
    future = population.merge(identifiers, how="cross")
    future["feature_cutoff"] = cutoff
    future["history_mean_yes"] = np.nan
    future["history_n_objects"] = np.nan
    future = freeze_history(train, future)
    future["history_last_vote_date"] = latest_date

    statpop = sources["statpop"]
    _require_columns(statpop, ["municipality_id", "year", "available_from", *DEMOGRAPHICS], "STATPOP")
    stats = statpop[["municipality_id", "year", "available_from", *DEMOGRAPHICS]].rename(columns={
        "year": "statpop_year", "available_from": "statpop_selection_from",
        **{name: f"statpop_{name}" for name in DEMOGRAPHICS},
    }).copy()
    stats["statpop_selection_from"] = _dates(stats.statpop_selection_from, "STATPOP selection dates")
    future = asof_join(future, stats, "statpop_selection_from")
    future = asof_join(future, election_wide(sources["elections"]), "election_selection_from")

    _require_columns(sources["typologies"], ["municipality_id", *TYPOLOGIES], "Typologies")
    typologies = sources["typologies"][["municipality_id", *TYPOLOGIES]].copy()
    typologies["municipality_id"] = typologies.municipality_id.astype("string")
    unique_keys(typologies, ["municipality_id"], "Typologies")
    future = future.merge(typologies, on="municipality_id", how="left", validate="many_to_one", sort=False)
    metadata = objects[["vote_key", *OBJECT_FIELDS]].rename(columns=OBJECT_FIELDS)
    for column in OBJECT_FIELDS.values():
        metadata[column] = metadata[column].astype("string")
    future = future.merge(metadata, on="vote_key", how="left", validate="many_to_one", sort=False)
    future["history_missing"] = future.history_mean_yes.isna()
    future["statpop_missing"] = future.statpop_year.isna()
    future["elections_missing"] = future[[f"party_share_{party}" for party in PARTIES.values()]].isna().all(axis=1)
    future["geography_id"] = "retrospective_fixed_2026-01-01"
    future["strict_forecast_ready"] = False
    population_values = pd.to_numeric(future.statpop_pop_total, errors="coerce").astype(float)
    if (population_values.notna() & (~np.isfinite(population_values) | population_values.lt(0))).any():
        raise ValueError("Invalid population predictor")
    future["log_population"] = np.log1p(population_values)

    future, political = add_political_features(future, objects)
    future, direction = add_direction_features(future, objects)
    poll_manifest = {"status": "not_supplied"}
    if "polls" in sources and sources["polls"] is not None:
        from scripts.modeling.poll_anchor import add_poll_features
        future, poll_manifest = add_poll_features(future, sources["polls"], as_of=cutoff)

    title = pd.Series("", index=objects.index, dtype="string")
    for field in ("titel_off_f", "titre_off_f", "titel_kurz_f"):
        if field in objects:
            available = objects[field].astype("string").fillna("").str.strip()
            title = title.mask(title.eq("") & available.ne(""), available)
    title_by_key = dict(zip(objects.vote_key, title))
    future["title_fr"] = future.vote_key.map(title_by_key)
    future = future.sort_values(["vote_date", "vote_id", "municipality_id"]).reset_index(drop=True)
    unique_keys(future, KEYS, "Future feature matrix")
    if len(future) != len(population) * len(objects):
        raise ValueError("A future source join changed the complete municipality-object population")
    forbidden = set(future) & OUTCOME_COLUMNS
    if forbidden:
        raise ValueError(f"Future predictors contain outcome columns: {sorted(forbidden)}")

    manifest = {
        "mode": "prospective_research_batch_fixed_2026_geography",
        "vote_date": str(voting_date.date()), "as_of_utc": _utc_iso(cutoff),
        "training_last_vote_date": str(latest_date.date()),
        "population_policy": "All municipalities appearing on the latest date of the supplied prepared training table",
        "municipalities": len(population), "objects": len(objects), "rows": len(future),
        "vote_ids": objects.vote_key.tolist(), "excluded_subsidiary_objects": subsidiary_count,
        "source_members_read": [*USED_SOURCES, *( ["polls"] if "polls" in sources and sources["polls"] is not None else [])],
        "current_ofs_outcomes_read": False, "future_outcome_columns": [],
        "history_policy": "Only prepared historical targets strictly before as_of; cumulative means frozen after the last training date",
        "source_selection_cutoff": "as_of, not the day before the future vote",
        "strict_forecast_ready": False,
        "political": political, "direction": direction, "polls": poll_manifest,
        "missing_rows": {name: int(future[name].isna().sum()) for name in
                         ["history_mean_yes", "log_population", *[f"party_share_{p}" for p in PARTIES.values()]]},
        "limitations": [
            "Historical source publication vintages are not certified; source selection dates include documented approximations.",
            "Municipalities and typologies use fixed 2026 geography, not an independently verified future electorate.",
            "Title directions are lexical proxies; the batch makes no accuracy guarantee.",
            "Weighted aggregates are population/electorate proxies, not a forecast weighted by actual future valid ballots.",
        ],
    }
    return future, manifest


def summarize_forecast(future, predictions):
    """Keep equal-municipality and explicitly approximate weighted means apart."""
    predictions = np.asarray(predictions, dtype=float)
    if predictions.ndim != 1 or len(predictions) != len(future):
        raise ValueError("Predictions must have exactly one value per future row")
    if not (np.isfinite(predictions) & (predictions >= 0) & (predictions <= 1)).all():
        raise ValueError("Forecast predictions must be finite proportions in [0, 1]")
    weight_column = "poll_population_weight" if "poll_population_weight" in future else "statpop_pop_total"
    if weight_column == "poll_population_weight":
        definition = "Electorate proxy: resident population * (1 - foreign share) * (1 - age 0-19 share); marginal product, excludes age 18-19"
    else:
        definition = "Resident-population proxy; includes minors and foreign residents, not eligible voters or valid ballots"
    rows = future[["vote_id", "vote_date", "title_fr", weight_column]].copy()
    rows["prediction"] = predictions
    records = []
    for (vote_id, vote_date), group in rows.groupby(["vote_id", "vote_date"], sort=True):
        weights = pd.to_numeric(group[weight_column], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(weights) & (weights > 0)
        weighted = float(np.average(group.prediction.to_numpy()[valid], weights=weights[valid])) if valid.any() else np.nan
        records.append({
            "vote_id": vote_id, "vote_date": pd.Timestamp(vote_date).date().isoformat(),
            "title_fr": group.title_fr.iloc[0], "municipalities": len(group),
            "mean_yes_share_unweighted": float(group.prediction.mean()),
            "weighted_yes_share_proxy": weighted,
            "weighted_municipalities": int(valid.sum()), "weight_coverage_share": float(valid.mean()),
            "weight_column": weight_column, "weight_definition": definition,
        })
    return pd.DataFrame(records)


def load_verified_candidate(output):
    """Verify frozen code/data/environment before loading current Python classes.

    A matching joblib hash alone is insufficient: its serialized objects use
    the class implementations currently imported from the workspace.
    """
    output = Path(output)
    model_path = output / "candidate_model.joblib"
    card = json.loads((output / "candidate_model_card.json").read_text())
    if digest(model_path) != card["model_sha256"]:
        raise ValueError("Candidate model hash differs from its model card")
    frozen, training, _ = verify_freeze(output)
    if card.get("frozen_signature") != frozen["signature"]:
        raise ValueError("Candidate model card does not match the frozen selection signature")
    if card.get("environment") != frozen["environment"]:
        raise ValueError("Candidate model card environment differs from the frozen environment")
    training_dates = _dates(training.vote_date, "training voting dates")
    training = training.loc[training_dates.between(
        _timestamp(card["training_start"], "model training_start"),
        _timestamp(card["training_end"], "model training_end"),
    )].copy()
    if training.empty or str(pd.to_datetime(training.vote_date).max().date()) != card["training_end"]:
        raise ValueError("Prepared training history does not match the model card end date")
    return joblib.load(model_path), training, card, frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Experiment directory with dataset.parquet and candidate_model artifacts")
    parser.add_argument("--vote-date", required=True, help="Future voting date, YYYY-MM-DD")
    parser.add_argument("--as-of", required=True, help="Predictor cutoff; YYYY-MM-DD means midnight UTC")
    parser.add_argument("--polls", type=Path, default=None,
                        help="Optional poll CSV; otherwise use data/external/polls/srg_gfs_polls.csv if present")
    args = parser.parse_args()
    captured_at = datetime.now(timezone.utc)
    voting_date = _timestamp(args.vote_date, "vote_date").normalize()
    cutoff = _timestamp(args.as_of, "as_of")
    capture = pd.Timestamp(captured_at).tz_localize(None)
    if not cutoff <= capture < voting_date:
        raise ValueError("A prospective batch requires as_of <= actual capture time < vote_date")

    output = args.output
    model_path = output / "candidate_model.joblib"
    card_path = output / "candidate_model_card.json"
    dataset_path = output / "dataset.parquet"
    data_manifest_path = output / "data_manifest.json"
    model, training, card, frozen = load_verified_candidate(output)

    sources, hashes = {}, {}
    for name in USED_SOURCES:
        path = ROOT / "data/processed" / SOURCES[name]
        sources[name] = pd.read_parquet(path)
        hashes[name] = {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
    poll_path = args.polls if args.polls is not None else (DEFAULT_POLLS if DEFAULT_POLLS.exists() else None)
    if poll_path is not None:
        sources["polls"] = pd.read_csv(poll_path, dtype={"vote_id": "string", "vote_key": "string"})
        hashes["polls"] = {"path": str(poll_path), "sha256": digest(poll_path)}
    future, manifest = build_future_frame(training, sources, voting_date, cutoff)
    # Centered spatial models require the complete selected population here.
    with threadpool_limits(limits=2):
        predictions = np.asarray(model.predict(future), dtype=float)
    summary = summarize_forecast(future, predictions)
    forecast = future[["municipality_id", "canton", "vote_id", "vote_date", "title_fr"]].copy()
    forecast["vote_date"] = forecast.vote_date.dt.strftime("%Y-%m-%d")
    forecast["prediction_yes_share"] = predictions
    prefix = "forecast_" + voting_date.strftime("%Y%m%d")
    names = {"predictions": f"{prefix}.csv", "summary": f"{prefix}_summary.csv",
             "features": f"{prefix}_features.parquet", "provenance": f"{prefix}_provenance.json"}
    if any((output / name).exists() for name in names.values()):
        raise FileExistsError("Forecast artifacts already exist; preserve the original captured batch")
    manifest.update({
        "captured_at_utc": captured_at.isoformat().replace("+00:00", "Z"),
        "captured_before_vote": True, "model_sha256": digest(model_path),
        "model_card_sha256": digest(card_path), "training_dataset_sha256": digest(dataset_path),
        "data_manifest_sha256": digest(data_manifest_path), "sources": hashes,
        "model_selection": card.get("selection"), "model_environment": card.get("environment"),
        "frozen_selection_signature": frozen["signature"],
        "verified_model_code": frozen["code"], "verified_model_environment": frozen["environment"],
        "forecast_code_sha256": digest(Path(__file__)),
        "source_snapshot_at_capture_not_certified_archived_at_as_of": True,
    })
    with TemporaryDirectory(prefix=".forecast-staging-", dir=output) as temporary:
        staged = Path(temporary)
        forecast.to_csv(staged / names["predictions"], index=False)
        summary.to_csv(staged / names["summary"], index=False)
        future.to_parquet(staged / names["features"], index=False)
        manifest["artifacts"] = {kind: {"file": name, "sha256": digest(staged / name)}
                                 for kind, name in names.items() if kind != "provenance"}
        manifest["signature"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, default=str).encode()).hexdigest()
        write_json(staged / names["provenance"], manifest)
        for kind in ("predictions", "summary", "features", "provenance"):
            (staged / names[kind]).replace(output / names[kind])
    print(json.dumps({"forecast": str(output / names["predictions"]),
                      "summary": str(output / names["summary"]),
                      "provenance": str(output / names["provenance"]),
                      "rows": len(forecast), "objects": int(forecast.vote_id.nunique()),
                      "captured_at_utc": manifest["captured_at_utc"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
