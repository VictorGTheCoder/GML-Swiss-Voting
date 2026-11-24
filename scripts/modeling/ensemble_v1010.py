"""V10.10 chronological convex ensemble of predeclared out-of-fold forecasts.

All families and candidates are declared without selecting the held-out
winner. Fit convex weights on completed earlier dates only. Compare level
and contrast stacking under one common ex-ante municipal ballot proxy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.turnout_v103 import load_ballots

FAMILIES = {
    "v101": ("expectation25", "expectation50", "expectation75", "expectation100", "walk_forward"),
    "v102": ("bias_control", "tone", "tone_volume", "tone_prominence"),
    "v103": ("last_reanchor", "pooled_reanchor", "domain_reanchor"),
    "v104": ("additive_ridge", "crossed_ridge", "domain_ridge", "margin_ridge", "domain_pooled_weights"),
    "v105": ("absolute25", "absolute50", "centered25", "centered50", "centered100"),
    "v106": ("abs_diag", "abs_shrink75", "abs_shrink25", "center_diag", "center_shrink75",
             "center_shrink25", "abs_anchor75", "center_anchor75"),
    "v107": ("mean_identity", "object_identity", "object_latent", "object_geo", "object_hybrid",
             "object_hybrid_strong", "object_hybrid_full"),
    "v108": tuple(f"{name}_{head}" for name in ("title_e5_16", "page_e5_16", "page_tfidf_16",
                  "page_e5_cues_16", "cues_only") for head in ("all", "local")),
    "v109": tuple(f"{name}_{lam}" for name in ("demographic_control", "income_means",
                  "income_distribution", "income_demographic") for lam in (30, 100)),
}
KEYS = ["vote_id", "municipality_id", "vote_date"]
METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")


def read_artifact(path, columns):
    m = json.loads((path / "manifest.json").read_text())
    p = path / "predictions.parquet"
    if m["status"] not in ("complete", "pilot_complete") or m["prediction_sha256"] != sha(p):
        raise ValueError(f"Invalid prediction artifact: {path}")
    d = pd.read_parquet(p, columns=[*KEYS, *columns])
    d["vote_id"] = d.vote_id.astype(str)
    d["municipality_id"] = d.municipality_id.astype(str)
    d["vote_date"] = pd.to_datetime(d.vote_date)
    if (len(d) != 138868 or d.vote_id.nunique() != 66 or d.vote_date.nunique() != 23
            or d.vote_date.ge("2023-01-01").any() or d.duplicated(KEYS).any()):
        raise ValueError(f"Invalid artifact population: {path}")
    return d.set_index(KEYS, verify_integrity=True).sort_index()


def gram(errors):
    """Equal-object contribution; no municipality pseudo-replication."""
    e = np.asarray(errors, float)
    if e.ndim != 2 or not len(e) or not np.isfinite(e).all():
        raise ValueError("Invalid errors")
    return e.T @ e / len(e)


def weights_from_history(history, day, prior, penalty, metric):
    """Only prior OOF errors, strict date cutoff and simplex constraints."""
    prior = np.asarray(prior, float)
    if (prior < 0).any() or not np.isclose(prior.sum(), 1):
        raise ValueError("Invalid prior")
    prev = [r for r in history if r["date"] < day]
    if len(prev) < 8 or len({r["date"] for r in prev}) < 3:
        return prior.copy(), len(prev)
    g = np.mean([r[metric] for r in prev], axis=0)
    n = len(prior)
    # Penalize changes in weights; scale relative to the historical error variance.
    ridge = penalty * max(float(np.diag(g).mean()), 1e-8)
    def objective(w):
        return float(w @ g @ w + ridge * np.square(w - prior).sum())
    def gradient(w):
        return 2 * g @ w + 2 * ridge * (w - prior)
    result = minimize(objective, prior, jac=gradient, method="SLSQP",
                      bounds=[(0., 1.)] * n,
                      constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.,
                                    "jac": lambda w: np.ones_like(w)}],
                      options={"ftol": 1e-12, "maxiter": 300})
    if not result.success:
        raise ValueError("Convex stack solver failed: " + result.message)
    w = np.clip(result.x, 0., 1.)
    return w / w.sum(), len(prev)


def split_prediction(x, exposure, national_weights, local_weights):
    """Use independently calibrated global level and local shape."""
    means = np.average(x, axis=0, weights=exposure)
    target = float(means @ national_weights)
    return shift_to(x @ local_weights, exposure, target)


def run(inputs, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve previous ensemble")
    base = read_artifact(inputs / "v103", ["reference", "reference_weight"])
    names = ["reference"]
    members = [("reference", "reference")]
    vectors = [base.reference.to_numpy(float)]
    manifest_hashes = {}
    for family, variants in FAMILIES.items():
        path = inputs / family
        f = read_artifact(path, ["reference", *variants])
        if not f.index.equals(base.index):
            raise ValueError("OOF population differs: " + family)
        if not np.allclose(f.reference, base.reference, atol=1e-8, rtol=0):
            raise ValueError("OOF references differ: " + family)
        manifest_hashes[family] = sha(path / "manifest.json")
        for name in variants:
            vectors.append(f[name].to_numpy(float))
            names.append(family + "__" + name)
            members.append((family, name))
    x = np.column_stack(vectors)
    if not np.isfinite(x).all() or (x < -1e-10).any() or (x > 1+1e-10).any():
        raise ValueError("Invalid base forecasts")
    families = ["reference", *FAMILIES]
    groups = [np.flatnonzero([f == k for f, _ in members]) for k in families]
    fmat = np.column_stack([x[:, ix].mean(axis=1) for ix in groups])
    equal = np.ones(len(families)) / len(families)
    half = equal * .5
    half[0] += .5
    family_balanced = np.zeros(len(names))
    for i, ix in enumerate(groups):
        family_balanced[ix] = equal[i] / len(ix)
    frame = base.reset_index()
    frame["row_index"] = np.arange(len(frame))
    outcomes = load_ballots()
    observed = {k: g.set_index("municipality_id", verify_integrity=True) for k, g in outcomes.groupby("vote_id")}
    hist, all_hist, rows, cantons, predictions, coefficients, residual_rows = [], [], [], [], [], [], []
    for day, cases in frame.groupby("vote_date", sort=True):
        pending, all_pending = [], []
        wa, n = weights_from_history(hist, day, equal, .1, "overall")
        wb, _ = weights_from_history(hist, day, half, .1, "overall")
        wc, _ = weights_from_history(hist, day, half, .02, "overall")
        wv, _ = weights_from_history(all_hist, day, family_balanced, .1, "overall")
        wn, _ = weights_from_history(hist, day, half, .1, "national")
        wl, _ = weights_from_history(hist, day, half, .1, "local")
        coefficients.append({"date": str(day.date()), "prior_objects": n,
                             "family_uniform": wa.tolist(), "family_reference": wb.tolist(),
                             "family_reference_weak": wc.tolist(), "all_variants": wv.tolist(),
                             "split_national": wn.tolist(), "split_local": wl.tolist()})
        for vote, v in cases.groupby("vote_id", sort=False):
            v = v.sort_values("municipality_id")
            ix = v.row_index.to_numpy(int)
            a, b = x[ix], fmat[ix]
            w = v.reference_weight.to_numpy(float)
            forecasts = {"reference": a[:, 0], "fixed_equal_families": b @ equal,
                         "fixed_half_reference": b @ half, "adaptive_family_uniform": b @ wa,
                         "adaptive_family_reference": b @ wb, "adaptive_family_reference_weak": b @ wc,
                         "adaptive_all_variants": a @ wv,
                         "split_level_local": split_prediction(b, w, wn, wl)}
            # Only now read the target data, score and prepare later-date history.
            actual = observed[vote].reindex(v.municipality_id)
            yes, no = actual.votes_yes.to_numpy(float), actual.votes_no.to_numpy(float)
            y = yes / (yes + no)
            if not np.isfinite(y).all():
                raise ValueError("Outcome alignment failed")
            e = b - y[:, None]
            centered = e - e.mean(axis=0)
            national_e = np.average(b, axis=0, weights=w) - yes.sum() / (yes+no).sum()
            pending.append({"date": day, "overall": gram(e), "local": gram(centered),
                            "national": np.outer(national_e, national_e)})
            all_pending.append({"date": day, "overall": gram(a-y[:, None])})
            residual_rows.append({"vote_id": vote, **dict(zip(families, e.mean(axis=0)))})
            block = v[KEYS].copy()
            block["yes_share"] = y
            fold = "2016-18" if day.year <= 2018 else "2019-20" if day.year <= 2020 else "2021-22"
            for name, p in forecasts.items():
                p = np.clip(p, 0., 1.)
                met, cs = multiscale(y, p, w, yes, no, actual.canton.astype(str).to_numpy())
                rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                             "fold": fold, "prior_objects": n, **met})
                cantons.extend({"variant": name, "vote_id": vote, **c} for c in cs)
                block[name] = p
                block[name+"_weight"] = w
            predictions.append(block)
        hist.extend(pending)
        all_hist.extend(all_pending)
    detail = pd.DataFrame(rows)
    summary = []
    for name, g in detail.groupby("variant", sort=False):
        if len(g) != 66 or g.vote_date.nunique() != 23:
            raise ValueError("Incomplete ensemble")
        summary.append({"variant": name, "objects": len(g), **{k: float(g[k].mean()) for k in METRICS},
                        "gain_interval": [0.,0.] if name=="reference" else
                        paired_date_bootstrap(detail,"reference",name)})
    if not np.isclose(summary[0]["mae_pp"], REFERENCE, atol=.0002, rtol=0):
        raise ValueError("Reference mismatch")
    output.mkdir(parents=True,exist_ok=True)
    detail.to_csv(output/"object_metrics.csv",index=False)
    detail.groupby(["variant","fold"])[list(METRICS)].mean().to_csv(output/"fold_metrics.csv")
    pd.DataFrame(cantons).to_csv(output/"canton_metrics.csv",index=False)
    pd.DataFrame(summary).to_csv(output/"summary.csv",index=False)
    pd.DataFrame(residual_rows).set_index("vote_id").corr().to_csv(output/"family_error_correlations.csv")
    pd.concat(predictions,ignore_index=True).to_parquet(output/"predictions.parquet",index=False)
    (output/"weights.json").write_text(json.dumps({"families":families,"variants":names,"weights":coefficients},indent=2))
    result={"status":"complete","strict_forecast_ready":False,"same_date_excluded":True,
            "comparison_targets_loaded":False,"families":FAMILIES,"candidate_count":len(names),
            "source_manifest_hashes":manifest_hashes,"prediction_sha256":sha(output/"predictions.parquet"),
            "summary":summary}
    (output/"manifest.json").write_text(json.dumps(result,indent=2,allow_nan=False))
    print("SUMMARY",json.dumps(summary,allow_nan=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    run(a.inputs,a.output)


if __name__=="__main__":
    main()
