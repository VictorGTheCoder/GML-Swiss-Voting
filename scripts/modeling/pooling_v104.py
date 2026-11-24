"""V10.4: aggregate cross-classified partial pooling of past forecast errors.

This is an ecological, municipality-cell analogue, not individual MRP.
No survey microdata or inferred individual preferences. Strict earlier dates
only, fixed candidates, common baseline and national anchor.
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
VARIANTS = {
    "reference": (None, 0., False),
    "additive_ridge": ("additive", 2., False),
    "crossed_ridge": ("crossed", 2., False),
    "domain_ridge": ("domain", 4., False),
    "margin_ridge": ("margin", 4., False),
    "domain_pooled_weights": ("domain", 4., True),
}


def cell_keys(frame):
    return list(zip(frame.language.astype(str), frame.urban.astype(str)))


def features(language, urban, domain, lm, um, mode):
    d = {"language=" + language: 1., "urban=" + urban: 1.}
    cell = language + "|" + urban
    if mode != "additive":
        d["cell=" + cell] = 1.
    if mode in ("domain", "margin"):
        d["domain_language=" + domain + "|" + language] = 1.
        d["domain_urban=" + domain + "|" + urban] = 1.
    if mode == "margin":
        d["lang_poll=" + str(lm) + "|" + language] = 1.
        d["urban_poll=" + str(um) + "|" + urban] = 1.
    return d


def fit_correction(history, day, keys, domain, lm, um, mode, alpha):
    # One aggregate cell per past object. Each object has total training
    # weight one, avoiding pseudo-replication from thousands of municipalities.
    prior = [r for r in history if r["day"] < day]
    if len({r["vote"] for r in prior}) < 8 or len({r["day"] for r in prior}) < 3:
        return np.zeros(len(keys)), len({r["vote"] for r in prior})
    vec = DictVectorizer()
    train = vec.fit_transform([
        features(r["language"], r["urban"], r["domain"], r["lm"], r["um"], mode)
        for r in prior
    ])
    model = Ridge(alpha=alpha, fit_intercept=False, solver="lsqr")
    model.fit(train, [r["residual"] for r in prior],
              sample_weight=[r["weight"] for r in prior])
    unique = sorted(set(keys))
    pred = model.predict(vec.transform([
        features(a, b, domain, lm, um, mode) for a, b in unique
    ]))
    by_key = dict(zip(unique, pred))
    return np.array([by_key[k] for k in keys]), len({r["vote"] for r in prior})


def apply_correction(p, w, correction):
    # Preserve pre-vote national anchor after clipping.
    return shift_to(p + correction, w, np.average(p, weights=w))


def history_cells(vote, day, keys, domain, lm, um, y, p):
    residual = y - p
    residual -= residual.mean()
    frame = pd.DataFrame({"language": [k[0] for k in keys],
                          "urban": [k[1] for k in keys], "residual": residual})
    grouped = frame.groupby(["language", "urban"]).residual.agg(["mean", "size"])
    return [{"day": day, "vote": vote, "language": a, "urban": b,
             "domain": domain, "lm": lm, "um": um, "residual": float(row["mean"]),
             "weight": float(row["size"] / len(y))}
            for (a, b), row in grouped.iterrows()]


def run(base, acquisition, fusion, turnout, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve earlier experiment")
    manifest = json.loads((turnout / "manifest.json").read_text())
    path = turnout / "predictions.parquet"
    if manifest["status"] != "complete" or manifest["prediction_sha256"] != sha(path):
        raise ValueError("V10.3 artifact hash mismatch")
    frozen = pd.read_parquet(path)
    frozen["vote_id"] = frozen.vote_id.astype(str)
    frozen["municipality_id"] = frozen.municipality_id.astype(str)
    if len(frozen) != 138868 or frozen.vote_id.nunique() != 66:
        raise ValueError("V10.3 population mismatch")
    groups = {k: g.set_index("municipality_id", verify_integrity=True)
              for k, g in frozen.groupby("vote_id")}
    _, cases = contexts(base, acquisition, fusion)
    outcomes = load_ballots()
    observed = {k: g.set_index("municipality_id", verify_integrity=True)
                for k, g in outcomes.groupby("vote_id")}
    history, rows, canton_rows, predictions = [], [], [], []
    for vote, day, v, _, lm, um in cases:
        f = groups[vote].reindex(v.municipality_id)
        p = f.reference.to_numpy(float)
        w = f.reference_weight.to_numpy(float)
        pooled = f.pooled_weights_only_weight.to_numpy(float)
        if not np.isfinite(np.column_stack([p, w, pooled])).all():
            raise ValueError("Unmatched frozen forecasts")
        keys = cell_keys(v)
        domain = str(v.object_domain_1.iloc[0])
        forecasts, support = {}, {}
        for name, (mode, alpha, use_pooled) in VARIANTS.items():
            if mode is None:
                forecasts[name] = (p.copy(), w)
                support[name] = 0
            else:
                correction, n = fit_correction(history, day, keys, domain, lm is not None,
                                               um is not None, mode, alpha)
                exposure = pooled if use_pooled else w
                forecasts[name] = (apply_correction(p, exposure, correction), exposure)
                support[name] = n
        # Outcomes are consulted only after all forecasts have been constructed.
        actual = observed[vote].reindex(v.municipality_id)
        y = v.yes_share.to_numpy(float)
        if not np.allclose(y, f.yes_share):
            raise ValueError("Frozen scoring population mismatch")
        yes, no = actual.votes_yes.to_numpy(float), actual.votes_no.to_numpy(float)
        canton = actual.canton.astype(str).to_numpy()
        block = v[["vote_id", "municipality_id", "vote_date", "yes_share"]].copy()
        fold = "2016-18" if day.year <= 2018 else "2019-20" if day.year <= 2020 else "2021-22"
        for name, (q, exposure) in forecasts.items():
            m, c = multiscale(y, q, exposure, yes, no, canton)
            common, _ = multiscale(y, q, w, yes, no, canton)
            rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                         "fold": fold, "prior_objects": support[name], **m,
                         "common_national_mae_pp": common["national_mae_pp"],
                         "common_canton_mae_pp": common["canton_mae_pp"]})
            canton_rows.extend({"variant": name, "vote_id": vote, **r} for r in c)
            block[name] = q
            block[name + "_weight"] = exposure
        predictions.append(block)
        history.extend(history_cells(vote, day, keys, domain, lm is not None, um is not None, y, p))
    detail = pd.DataFrame(rows)
    summary = []
    extra = ["common_national_mae_pp", "common_canton_mae_pp"]
    for name, group in detail.groupby("variant", sort=False):
        if len(group) != 66 or group.vote_date.nunique() != 23:
            raise ValueError("Incomplete benchmark")
        summary.append({"variant": name, "objects": len(group),
                        "covered_objects": int(group.prior_objects.gt(0).sum()),
                        **{m: float(group[m].mean()) for m in [*METRICS, *extra]},
                        "gain_interval": [0., 0.] if name == "reference" else
                        paired_date_bootstrap(detail, "reference", name)})
    if not np.isclose(summary[0]["mae_pp"], REFERENCE, atol=.0002, rtol=0):
        raise ValueError("Reference mismatch")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    detail.groupby(["variant", "fold"])[list(METRICS) + extra].mean().to_csv(output / "fold_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    result = {"status": "complete", "strict_forecast_ready": False,
              "source_prediction_sha256": sha(path),
              "prediction_sha256": sha(output / "predictions.parquet"),
              "summary": summary}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "acquisition", "fusion", "turnout", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    run(a.base, a.acquisition, a.fusion, a.turnout, a.output)


if __name__ == "__main__":
    main()
