"""V10.5: direct canton models trained on strictly earlier aggregate outcomes.

Historical canton valid ballot shares are targets, never target-date features.
The municipal baseline remains frozen; direct ridge levels and centered canton
profiles are independent of the municipal model until explicit blending.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import Ridge

from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.spatial_margins_v81 import contexts
from scripts.modeling.turnout_v103 import load_ballots

METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")
CATS = ("object_domain_1", "object_domain_2", "object_domain_3", "object_legal_form")
SIGNS = tuple("political_direction_" + p for p in (
    "plr", "pdc", "ps", "udc", "pev", "verts", "pvl", "pbd", "centre",
    "federal_council", "parliament",
))
NUMS = SIGNS + ("political_nr_yes_fraction", "political_sr_yes_fraction",
                "political_national_yes_fraction_known")
VARIANTS = ("reference", "pooled_weights_control", "absolute25", "absolute50",
            "centered25", "centered50", "centered100")


def feature_map(canton, obj):
    f = {"canton=" + canton: 1.}
    for name in CATS:
        value = str(obj.get(name, "unknown"))
        key = name + "=" + value
        f[key] = 1.
        f[canton + "|" + key] = 1.
    for name in NUMS:
        value = obj.get(name, np.nan)
        if pd.notna(value) and np.isfinite(float(value)):
            f[name] = float(value)
            f[canton + "|" + name] = float(value)
        else:
            f[name + "_missing"] = 1.
    return f


def direct_forecasts(history, day, obj, cantons):
    prior = history.loc[history.vote_date.lt(day)]
    if prior.vote_id.nunique() < 20:
        raise ValueError("Insufficient direct training history")
    features = [feature_map(str(c), row) for c, row in
                zip(prior.canton, prior.to_dict("records"))]
    vec = DictVectorizer()
    x = vec.fit_transform(features)
    q = vec.transform([feature_map(c, obj) for c in cantons])
    weights = 1. / prior.groupby("vote_id").canton.transform("size")
    pred = {}
    for name, target, alpha in (("absolute", "share", 2.), ("centered", "contrast", 4.)):
        model = Ridge(alpha=alpha, solver="lsqr")
        model.fit(x, prior[target], sample_weight=weights)
        pred[name] = model.predict(q)
    return pred, int(prior.vote_id.nunique())


def aggregate(p, w, canton, labels):
    return np.array([np.average(p[canton == c], weights=w[canton == c]) for c in labels])


def apply_targets(p, w, canton, labels, target, blend):
    result = p.copy()
    for c, t in zip(labels, target):
        mask = canton == c
        current = np.average(p[mask], weights=w[mask])
        goal = np.clip((1. - blend) * current + blend * t, 0., 1.)
        result[mask] = shift_to(p[mask], w[mask], goal)
    return result


def run(base, acquisition, fusion, turnout, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve earlier experiments")
    manifest = json.loads((turnout / "manifest.json").read_text())
    source = turnout / "predictions.parquet"
    if manifest["status"] != "complete" or manifest["prediction_sha256"] != sha(source):
        raise ValueError("Frozen turnout artifact mismatch")
    frozen = pd.read_parquet(source)
    for key in ("vote_id", "municipality_id"):
        frozen[key] = frozen[key].astype(str)
    if len(frozen) != 138868 or frozen.vote_id.nunique() != 66:
        raise ValueError("Frozen population mismatch")
    groups = {k: g.set_index("municipality_id", verify_integrity=True)
              for k, g in frozen.groupby("vote_id")}
    data, cases = contexts(base, acquisition, fusion)
    fields = [x for x in (*CATS, *NUMS) if x in data]
    metadata = data[["vote_id", "vote_date", *fields]].drop_duplicates()
    if metadata.vote_id.duplicated().any():
        raise ValueError("Nonconstant object features")
    objects = metadata.set_index("vote_id")
    outcomes = load_ballots()
    outcomes["canton"] = outcomes.canton.astype(str)
    hist = outcomes.groupby(["vote_id", "vote_date", "canton"], as_index=False)[
        ["votes_yes", "votes_no"]].sum()
    hist["valid"] = hist.votes_yes + hist.votes_no
    hist = hist[hist.valid.gt(0)].copy()
    hist["share"] = hist.votes_yes / hist.valid
    hist["contrast"] = hist.share - (
        hist.groupby("vote_id").votes_yes.transform("sum") /
        hist.groupby("vote_id").valid.transform("sum"))
    hist = hist.merge(metadata, on=["vote_id", "vote_date"], validate="many_to_one")
    observed = {k: g.set_index("municipality_id", verify_integrity=True)
                for k, g in outcomes.groupby("vote_id")}
    rows, canton_rows, direct_rows, predictions = [], [], [], []
    for vote, day, v, _, _, _ in cases:
        f = groups[vote].reindex(v.municipality_id)
        p = f.reference.to_numpy(float)
        w = f.reference_weight.to_numpy(float)
        pooled = f.pooled_weights_only_weight.to_numpy(float)
        if not np.isfinite(np.column_stack([p, w, pooled])).all():
            raise ValueError("Unmatched baseline")
        canton = v.canton.astype(str).to_numpy()
        labels = np.unique(canton)
        if any(pooled[canton == c].sum() <= 0 for c in labels):
            raise ValueError("Canton without weights")
        cweights = np.array([pooled[canton == c].sum() for c in labels])
        anchor = np.average(p, weights=pooled)
        direct, n = direct_forecasts(hist, day, objects.loc[vote].to_dict(), labels)
        absolute = np.clip(direct["absolute"], 0., 1.)
        centered = shift_to(anchor + direct["centered"], cweights, anchor)
        forecasts = {"reference": (p, w), "pooled_weights_control": (p, pooled)}
        for name, target, blend in (("absolute25", absolute, .25), ("absolute50", absolute, .5),
                                    ("centered25", centered, .25), ("centered50", centered, .5),
                                    ("centered100", centered, 1.)):
            forecasts[name] = (apply_targets(p, pooled, canton, labels, target, blend), pooled)
        actual = observed[vote].reindex(v.municipality_id)
        y = v.yes_share.to_numpy(float)
        if not np.allclose(y, f.yes_share) or not np.array_equal(canton, actual.canton.to_numpy()):
            raise ValueError("Scoring population mismatch")
        yes, no = actual.votes_yes.to_numpy(float), actual.votes_no.to_numpy(float)
        valid = yes + no
        obs = aggregate(y, valid, canton, labels)
        bottom = aggregate(p, pooled, canton, labels)
        for i, c in enumerate(labels):
            direct_rows.append({"vote_id": vote, "vote_date": str(day.date()), "canton": c,
                                "prior_objects": n, "weight": cweights[i], "observed": obs[i],
                                "bottom_up": bottom[i], "absolute": absolute[i],
                                "centered": centered[i], "national_anchor": anchor})
        block = v[["vote_id", "municipality_id", "vote_date", "yes_share"]].copy()
        fold = "2016-18" if day.year <= 2018 else "2019-20" if day.year <= 2020 else "2021-22"
        for name, (q, exposure) in forecasts.items():
            m, c = multiscale(y, q, exposure, yes, no, canton)
            common, _ = multiscale(y, q, w, yes, no, canton)
            rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                         "fold": fold, "prior_objects": n, **m,
                         "common_national_mae_pp": common["national_mae_pp"],
                         "common_canton_mae_pp": common["canton_mae_pp"]})
            canton_rows.extend({"variant": name, "vote_id": vote, **r} for r in c)
            block[name] = q
            block[name + "_weight"] = exposure
        predictions.append(block)
    detail = pd.DataFrame(rows)
    direct_detail = pd.DataFrame(direct_rows)
    direct_scores = {}
    for name in ("bottom_up", "absolute", "centered"):
        err = (direct_detail[name] - direct_detail.observed).abs() * 100
        direct_scores[name] = float(err.groupby(direct_detail.vote_id).mean().mean())
    summary = []
    extra = ["common_national_mae_pp", "common_canton_mae_pp"]
    for name, group in detail.groupby("variant", sort=False):
        if len(group) != 66 or group.vote_date.nunique() != 23:
            raise ValueError("Incomplete benchmark")
        summary.append({"variant": name, "objects": len(group),
                        "covered_objects": len(group), "minimum_prior_objects": int(group.prior_objects.min()),
                        **{m: float(group[m].mean()) for m in [*METRICS, *extra]},
                        "gain_interval": [0., 0.] if name == "reference" else
                        paired_date_bootstrap(detail, "reference", name)})
    if not np.isclose(summary[0]["mae_pp"], REFERENCE, atol=.0002, rtol=0):
        raise ValueError("Reference mismatch")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    detail.groupby(["variant", "fold"])[list(METRICS) + extra].mean().to_csv(output / "fold_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    direct_detail.to_csv(output / "direct_canton_predictions.csv", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    result = {"status": "complete", "strict_forecast_ready": False, "fields": fields,
              "source_prediction_sha256": sha(source), "direct_canton_mae": direct_scores,
              "direct_canton_sha256": sha(output / "direct_canton_predictions.csv"),
              "prediction_sha256": sha(output / "predictions.parquet"), "summary": summary}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print("DIRECT", json.dumps(direct_scores), flush=True)
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "acquisition", "fusion", "turnout", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    run(a.base, a.acquisition, a.fusion, a.turnout, a.output)


if __name__ == "__main__":
    main()
