"""V13.3: scoring-only diagnosis of the remaining aggregate error budget."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.modeling.ensemble_v1010 import artifact_root, read_artifact
from scripts.modeling.semantic_poll_comparison_v4 import sha

NAMES = {"reference": 7.229527497606818, "institution_text": 6.955753873756506}
METRICS = ["mae_pp", "centered_mae_pp", "median_offset_oracle_pp", "local_oracle_gain_pp"]


def offset_diagnosis(y, p):
    """Unbounded constant-shift L1 oracle; never a forecast or attainable bound for other models."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    if y.ndim != 1 or y.shape != p.shape or not len(y):
        raise ValueError("Invalid scoring vectors")
    if not np.isfinite(np.column_stack([y, p])).all() or ((y < 0) | (y > 1) | (p < 0) | (p > 1)).any():
        raise ValueError("Invalid shares")
    e = 100 * (p - y)
    mae = float(np.abs(e).mean())
    centered = float(np.abs(e - e.mean()).mean())
    oracle = float(np.abs(e - np.median(e)).mean())
    return {"mae_pp": mae, "centered_mae_pp": centered,
            "median_offset_oracle_pp": oracle, "local_oracle_gain_pp": mae - oracle}


def date_interval(detail, column, seed=133, draws=5000):
    # Resample whole dates, retaining equal weight per object, not per date.
    g = detail.groupby("vote_date")[column].agg(["sum", "size"])
    if g.empty or draws < 1:
        raise ValueError("Invalid bootstrap")
    idx = np.random.default_rng(seed).integers(0, len(g), size=(draws, len(g)))
    samples = g["sum"].to_numpy()[idx].sum(axis=1) / g["size"].to_numpy()[idx].sum(axis=1)
    return np.quantile(samples, [.025, .975]).tolist()


def run(source, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve prior diagnostics")
    root = artifact_root(source)
    frame = read_artifact(source, ["yes_share", *NAMES]).reset_index()
    labels = pd.read_csv(root / "object_metrics.csv", dtype={"vote_id": str})
    labels = labels[labels.variant.eq("institution_text")].set_index("vote_id", verify_integrity=True)
    if set(labels.index) != set(frame.vote_id):
        raise ValueError("Object labels mismatch")
    rows = []
    for (day, vote), g in frame.groupby(["vote_date", "vote_id"], sort=True):
        label = labels.loc[vote]
        if pd.Timestamp(label.vote_date) != day:
            raise ValueError("Object date mismatch")
        for name in NAMES:
            rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                         "fold": label["fold"], "domain": label["domain"],
                         **offset_diagnosis(g.yes_share, g[name])})
    detail = pd.DataFrame(rows)
    summaries = []
    for name, g in detail.groupby("variant", sort=False):
        if len(g) != 66 or g.vote_date.nunique() != 23:
            raise ValueError("Unexpected diagnostic population")
        mean = g[METRICS].mean().to_dict()
        if not np.isclose(mean["mae_pp"], NAMES[name], atol=2e-4, rtol=0):
            raise ValueError("Reference changed")
        summaries.append({"variant": name, **mean,
                          "oracle_gain_interval": date_interval(g, "local_oracle_gain_pp"),
                          "oracle_remaining_interval": date_interval(g, "median_offset_oracle_pp"),
                          "objects_oracle_over_4pp": int(g.median_offset_oracle_pp.gt(4).sum())})
    # Existing multiscale scores: retain their original ex-ante weighting; no new ballots read.
    original = pd.read_csv(root / "object_metrics.csv", dtype={"vote_id": str})
    original = original[original.variant.isin(NAMES)].copy()
    matched = detail.merge(original[["variant", "vote_id", "mae_pp", "centered_mae_pp",
                                     "national_mae_pp", "canton_mae_pp"]],
                           on=["variant", "vote_id"], validate="one_to_one", suffixes=("", "_original"))
    if len(matched) != len(detail):
        raise ValueError("Incomplete scoring join")
    for metric in ("mae_pp", "centered_mae_pp"):
        if not np.allclose(matched[metric], matched[metric + "_original"], atol=1e-6, rtol=0):
            raise ValueError("Original metric mismatch")
    detail = matched.drop(columns=["mae_pp_original", "centered_mae_pp_original"])
    # Compare models on identical objects; descriptive, not model selection.
    paired = detail.pivot(index=["vote_date", "vote_id"], columns="variant", values="median_offset_oracle_pp")
    delta = (paired.reference - paired.institution_text).rename("gain_pp").reset_index()
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_diagnostic.csv", index=False)
    for col in ("fold", "domain"):
        detail.groupby(["variant", col])[METRICS + ["national_mae_pp", "canton_mae_pp"]].agg(
            ["mean", "size"]).to_csv(output / f"{col}_diagnostic.csv")
    # Across-commune temporal error distribution only, no municipality ranking exported.
    local = []
    for name in NAMES:
        err = frame[name].sub(frame.yes_share).abs().mul(100)
        avg = err.groupby(frame.municipality_id).mean()
        local.append({"variant": name, "municipalities": len(avg),
                      "mae_quantiles_pp": avg.quantile([.1, .5, .9]).tolist()})
    result = {"status": "diagnostic_complete", "prediction_model_changed": False,
              "oracle_scoring_only": True, "objects": 66, "dates": 23, "rows": len(frame),
              "prediction_sha256": sha(root / "predictions.parquet"), "summary": summaries,
              "oracle_difference_interval": date_interval(delta, "gain_pp"), "local_distribution": local}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print("SUMMARY", json.dumps(result, allow_nan=False), flush=True)
    print("DOMAIN", detail.groupby(["variant", "domain"])[METRICS].mean().to_json(), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()
