"""V12.4: complementary national/local forecasts and date sensitivity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.modeling.ensemble_v1010 import (
    KEYS,
    METRICS,
    artifact_root,
    gram,
    read_artifact,
    split_prediction,
    weights_from_history,
)
from scripts.modeling.expectations_v101 import multiscale
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.turnout_v103 import load_ballots

BASE = ("v113_institution", "pooled_exact")
NAMES = ("reference", "v108_tfidf", *BASE, "fixed_half",
         "pooled_level_institution_local", "institution_level_pooled_local", "adaptive_split")


def date_weights(history, day):
    prior = np.array([.5, .5])
    national, n = weights_from_history(history, day, prior, .1, "national")
    local, _ = weights_from_history(history, day, prior, .1, "local")
    return national, local, n


def forecasts(x, w, national, local):
    return {
        "fixed_half": x.mean(axis=1),
        "pooled_level_institution_local": split_prediction(x, w, [0., 1.], [1., 0.]),
        "institution_level_pooled_local": split_prediction(x, w, [1., 0.], [0., 1.]),
        "adaptive_split": split_prediction(x, w, national, local),
    }


def date_sensitivity(detail, candidate, reference="v113_institution"):
    p = detail.pivot(index=["vote_date", "vote_id"], columns="variant", values="mae_pp")
    gain = p[reference] - p[candidate]
    dates = gain.index.get_level_values("vote_date")
    return [{"excluded_date": str(day), "gain_pp": float(gain[dates != day].mean())}
            for day in dates.unique()]


def run(source, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve prior experiments")
    root = artifact_root(source)
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["coverage"] != dict.fromkeys(
        ("pooled_exact", "split_title_body", "split_question_mechanism"), 41
    ):
        raise ValueError("Coverage mismatch")
    frame = read_artifact(source, ["reference_weight", "yes_share", "reference",
                                   "v108_tfidf", *BASE]).reset_index()
    labels = pd.read_csv(root / "object_metrics.csv", dtype={"vote_id": str})
    labels = labels[labels.variant.eq("pooled_exact")].set_index("vote_id", verify_integrity=True)
    ballots = load_ballots()
    observed = {k: g.set_index("municipality_id", verify_integrity=True)
                for k, g in ballots.groupby("vote_id")}
    history, rows, cantons, blocks, weights = [], [], [], [], []
    for day, daily in frame.groupby("vote_date", sort=True):
        national, local, n = date_weights(history, day)
        weights.append({"date": str(day.date()), "prior_objects": n,
                        "national": national.tolist(), "local": local.tolist()})
        pending = []
        for vote, v in daily.groupby("vote_id", sort=False):
            x = v[list(BASE)].to_numpy(float)
            w = v.reference_weight.to_numpy(float)
            preds = {name: v[name].to_numpy(float) for name in NAMES[:4]}
            preds.update(forecasts(x, w, national, local))
            # All forecasts fixed before the scoring-only target access.
            actual = observed[vote].reindex(v.municipality_id)
            yes, no = actual.votes_yes.to_numpy(float), actual.votes_no.to_numpy(float)
            y = yes / (yes + no)
            if not np.allclose(y, v.yes_share, atol=1e-8, rtol=0):
                raise ValueError("Target alignment mismatch")
            e = x - y[:, None]
            national_e = np.average(x, axis=0, weights=w) - yes.sum() / (yes + no).sum()
            pending.append({"date": day, "national": np.outer(national_e, national_e),
                            "local": gram(e - e.mean(axis=0))})
            block = v[KEYS + ["yes_share", "reference_weight"]].copy()
            for name, p in preds.items():
                metrics, cs = multiscale(y, p, w, yes, no, actual.canton.astype(str).to_numpy())
                rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                             "fold": labels.loc[vote, "fold"], "domain": labels.loc[vote, "domain"],
                             **metrics})
                cantons.extend({"variant": name, "vote_id": vote, **c} for c in cs)
                block[name] = p
            blocks.append(block)
        history.extend(pending)
    detail = pd.DataFrame(rows)
    summary, sensitivity = [], []
    for name, g in detail.groupby("variant", sort=False):
        if len(g) != 66 or g.vote_date.nunique() != 23:
            raise ValueError("Incomplete comparison")
        summary.append({"variant": name, "objects": len(g),
                        **{k: float(g[k].mean()) for k in METRICS},
                        "gain_interval": paired_date_bootstrap(detail, "reference", name)
                        if name != "reference" else [0., 0.],
                        "vs_v113_interval": paired_date_bootstrap(detail, BASE[0], name)
                        if name != BASE[0] else [0., 0.]})
        sensitivity.extend({"variant": name, **r} for r in date_sensitivity(detail, name))
    checks = {"reference": 7.229527497606818, "v108_tfidf": 6.988599997055331,
              BASE[0]: 6.955753873756506, BASE[1]: 7.118590149986709}
    for row in summary:
        if row["variant"] in checks and not np.isclose(
            row["mae_pp"], checks[row["variant"]], atol=2e-4, rtol=0
        ):
            raise ValueError("Comparator changed")
    predictions = pd.concat(blocks, ignore_index=True)
    if len(predictions) != 138868 or predictions.duplicated(KEYS).any():
        raise ValueError("Population changed")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    for col in ("fold", "domain"):
        detail.groupby(["variant", col])[list(METRICS)].mean().to_csv(output / f"{col}_metrics.csv")
    pd.DataFrame(cantons).to_csv(output / "canton_metrics.csv", index=False)
    pd.DataFrame(sensitivity).to_csv(output / "date_sensitivity.csv", index=False)
    errors = predictions[list(NAMES)].sub(predictions.yes_share, axis=0).abs() * 100
    errors.groupby(predictions.municipality_id).mean().to_csv(output / "municipality_metrics.csv")
    predictions.to_parquet(output / "predictions.parquet", index=False)
    pd.DataFrame(summary).to_csv(output / "summary.csv", index=False)
    (output / "weights.json").write_text(json.dumps(weights, indent=2))
    result = {"status": "complete", "strict_forecast_ready": False,
              "comparison_targets_loaded": False, "source_manifest_sha256": sha(root / "manifest.json"),
              "prediction_sha256": sha(output / "predictions.parquet"), "summary": summary}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print("SUMMARY", json.dumps(summary, allow_nan=False), flush=True)
    print("DATE_SENSITIVITY", pd.DataFrame(sensitivity).groupby("variant").gain_pp.agg(
        ["min", "max"]).to_json(), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    run(a.source, a.output)


if __name__ == "__main__":
    main()
