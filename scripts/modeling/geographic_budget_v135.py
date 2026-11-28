"""V13.5: scoring-only between/within-canton error decomposition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.modeling.affine_budget_v134 import EXPECTED_SHA
from scripts.modeling.ensemble_v1010 import KEYS, artifact_root, read_artifact
from scripts.modeling.error_budget_v133 import NAMES, date_interval, offset_diagnosis
from scripts.modeling.expectations_v101 import multiscale
from scripts.modeling.semantic_poll_comparison_v4 import sha
from scripts.modeling.turnout_v103 import SOURCE, load_ballots

ORACLES = ["canton_offset_oracle_pp", "canton_offset_gain_pp"]
SQUARES = ["mse_pp2", "global_bias_pp2", "between_canton_pp2", "within_canton_pp2"]


def geographic_diagnosis(y, p, cantons):
    """Equal-municipality L1 oracle and exact L2 decomposition, not forecasts."""
    result = offset_diagnosis(y, p)
    e = 100 * (np.asarray(p, float) - np.asarray(y, float))
    c = np.asarray(cantons)
    if c.shape != e.shape or pd.isna(c).any():
        raise ValueError("Invalid canton mapping")
    c = c.astype(str)
    if np.isin(c, ["", "nan", "None", "<NA>"]).any():
        raise ValueError("Missing canton")
    within_l1, between, within = 0., 0., 0.
    overall = float(e.mean())
    for canton in np.unique(c):
        x = e[c == canton]
        within_l1 += float(np.abs(x - np.median(x)).sum())
        between += len(x) * float((x.mean() - overall) ** 2)
        within += float(np.square(x - x.mean()).sum())
    oracle = within_l1 / len(e)
    result.update(canton_offset_oracle_pp=oracle,
                  canton_offset_gain_pp=result["median_offset_oracle_pp"] - oracle,
                  mse_pp2=float(np.square(e).mean()),
                  global_bias_pp2=overall ** 2,
                  between_canton_pp2=between / len(e),
                  within_canton_pp2=within / len(e))
    if result["canton_offset_gain_pp"] < -1e-8 or not np.isclose(
        result["mse_pp2"], sum(result[k] for k in SQUARES[1:]), atol=1e-8, rtol=0
    ):
        raise ValueError("Decomposition invariant failed")
    return result


def match_scoring_geography(frame, outcomes):
    """Match only exact object/date/municipality keys; no fallback or silent drops."""
    cols = [*KEYS, "canton", "votes_yes", "votes_no"]
    actual = outcomes[cols].copy()
    for k in ("vote_id", "municipality_id"):
        actual[k] = actual[k].astype(str)
    actual["vote_date"] = pd.to_datetime(actual.vote_date)
    if actual.vote_date.ge("2023-01-01").any():
        raise ValueError("Comparison outcomes forbidden")
    actual = actual[actual.vote_id.isin(frame.vote_id)]
    joined = frame.merge(actual, on=KEYS, how="left", validate="one_to_one", indicator=True)
    if len(joined) != len(frame) or not joined["_merge"].eq("both").all():
        raise ValueError("Incomplete geography join")
    ballots = joined.votes_yes + joined.votes_no
    if (ballots <= 0).any() or not np.allclose(
        joined.votes_yes / ballots, joined.yes_share, atol=1e-8, rtol=0
    ):
        raise ValueError("Scoring counts differ from immutable outcomes")
    return joined.drop(columns="_merge")


def run(source, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve prior diagnostic")
    root = artifact_root(source)
    if sha(root / "predictions.parquet") != EXPECTED_SHA:
        raise ValueError("Unexpected immutable prediction bundle")
    frame = read_artifact(source, ["yes_share", "reference_weight", *NAMES]).reset_index()
    frame = match_scoring_geography(frame, load_ballots())
    original = pd.read_csv(root / "object_metrics.csv", dtype={"vote_id": str, "vote_date": str})
    original = original[original.variant.isin(NAMES)]
    rows = []
    for (day, vote), group in frame.groupby(["vote_date", "vote_id"], sort=True):
        for name in NAMES:
            met, _ = multiscale(group.yes_share, group[name], group.reference_weight,
                                group.votes_yes, group.votes_no, group.canton)
            diagnostic = geographic_diagnosis(group.yes_share, group[name], group.canton)
            rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                         "cantons": met["cantons"], **diagnostic,
                         "national_mae_pp": met["national_mae_pp"],
                         "canton_mae_pp": met["canton_mae_pp"]})
    detail = pd.DataFrame(rows)
    keys = ["variant", "vote_id", "vote_date"]
    conventional = ["mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp"]
    matched = detail.merge(original[keys + conventional + ["fold", "domain"]],
                           on=keys, validate="one_to_one", suffixes=("", "_original"))
    if len(matched) != len(detail) or len(matched) != len(original):
        raise ValueError("Incomplete original metric join")
    for metric in conventional:
        if not np.allclose(matched[metric], matched[metric + "_original"], atol=1e-8, rtol=0):
            raise ValueError("Original metric mismatch: " + metric)
    detail = matched.drop(columns=[k + "_original" for k in conventional])
    metrics = conventional + ["median_offset_oracle_pp", *ORACLES, *SQUARES]
    summary = []
    for name, group in detail.groupby("variant", sort=False):
        if len(group) != 66 or group.vote_date.nunique() != 23:
            raise ValueError("Unexpected scoring population")
        avg = group[metrics].mean().to_dict()
        if not np.isclose(avg["mae_pp"], NAMES[name], atol=2e-4, rtol=0):
            raise ValueError("Historical reference mismatch")
        summary.append({"variant": name, **avg,
                        "remaining_interval": date_interval(group, ORACLES[0], seed=135),
                        "gain_interval": date_interval(group, ORACLES[1], seed=135),
                        "objects_remaining_over_4pp": int(group[ORACLES[0]].gt(4).sum())})
    paired = detail.pivot(index=["vote_date", "vote_id"], columns="variant", values=ORACLES[0])
    delta = (paired.reference - paired.institution_text).rename("gain_pp").reset_index()
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_diagnostic.csv", index=False)
    for column in ("fold", "domain"):
        detail.groupby(["variant", column])[metrics].agg(["mean", "size"]).to_csv(
            output / f"{column}_diagnostic.csv")
    manifest = {"status": "diagnostic_complete", "oracle_scoring_only": True,
                "prediction_model_changed": False, "objects": 66, "dates": 23,
                "rows": len(frame), "geography_coverage": 1.,
                "prediction_sha256": EXPECTED_SHA, "geography_source_sha256": sha(SOURCE),
                "summary": summary, "paired_remaining_difference_interval":
                date_interval(delta, "gain_pp", seed=135)}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False),
                                         encoding="utf-8")
    print("SUMMARY", json.dumps(manifest, allow_nan=False), flush=True)
    print("DOMAIN", detail.groupby(["variant", "domain"])[metrics].mean().to_json(), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()
