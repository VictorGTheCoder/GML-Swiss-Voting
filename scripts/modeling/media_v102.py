"""Historical aggregate media-tone pilot, using dated interim reports only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.modeling.diagnose_v5_errors import load_outcomes
from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.spatial_margins_v81 import contexts, joint_adjust, observation_system

VARIANTS = ("reference", "bias_control", "tone", "tone_volume", "tone_prominence")
METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")


def validate_media(media):
    if media.duplicated("vote_key").any():
        raise ValueError("Duplicate object")
    dates = pd.to_datetime(media.vote_date)
    if not dates.between("2016-01-01", "2022-12-31").all():
        raise ValueError("Outside development period")
    if not (pd.to_datetime(media.published_at) <= dates - pd.Timedelta(days=1)).all():
        raise ValueError("Media publication too late")
    if not media.tone.between(-100, 100).all() or not media.articles.gt(0).all():
        raise ValueError("Invalid media metric")
    if not media.weeks.between(1, 12).all():
        raise ValueError("Invalid observation period")
    if not media.source_url.str.startswith("https://www.foeg.uzh.ch/").all():
        raise ValueError("Unapproved source")
    # Count a combined reform once in the date denominator.
    distinct = media.drop_duplicates(["vote_date", "report_label"])
    totals = distinct.groupby("vote_date").articles.sum()
    return media.assign(prominence=media.articles / media.vote_date.map(totals))


def features(row, variant):
    tone = row.tone / 50.
    if variant == "bias_control":
        return np.array([1.])
    if variant == "tone":
        return np.array([1., tone])
    if variant == "tone_volume":
        return np.array([1., tone, np.log(row.articles / row.weeks / 25.)])
    return np.array([1., tone, row.prominence - .33])


def correction(history, row, variant, day):
    if variant == "reference" or row is None:
        return 0.
    earlier = [h for h in history if h[0] < day]
    if len(earlier) < 6 or len({h[0] for h in earlier}) < 2:
        return 0.
    x = np.stack([features(h[1], variant) for h in earlier])
    y = np.array([h[2] for h in earlier])
    # Prespecified shrinkage toward zero; fixed scale and cap, not optimized.
    coef = np.linalg.solve(x.T @ x + 8. * np.eye(x.shape[1]), x.T @ y)
    return float(np.clip(features(row, variant) @ coef, -.10, .10))


def run(base, acquisition, fusion, source, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve earlier result")
    media = validate_media(pd.read_csv(source, dtype={"vote_key": str}))
    by_key = {str(r.vote_key): r for r in media.itertuples()}
    _, cases = contexts(base, acquisition, fusion)
    observed_keys = {str(v.vote_key.iloc[0]): str(day.date()) for _, day, v, _, _, _ in cases}
    if any(observed_keys.get(str(r.vote_key)) != r.vote_date for r in media.itertuples()):
        raise ValueError("Object identity or date mismatch")
    outcomes = load_outcomes()
    outcome_groups = {str(k): g.set_index("municipality_id", verify_integrity=True)
                      for k, g in outcomes.groupby("vote_id")}
    history, rows, canton_rows, predictions, audit = [], [], [], [], []
    for vote, day, v, f, lm, um in cases:
        row = by_key.get(str(v.vote_key.iloc[0]))
        w = v.weight.to_numpy(float)
        p = f.v8_reference.to_numpy(float)
        a, z, b, i = observation_system(w, v.language.to_numpy(), v.urban.to_numpy(), lm, um)
        baseline = float(np.average(p, weights=w))
        deltas = {name: correction(history, row, name, day) for name in VARIANTS}
        forecasts = {
            name: joint_adjust(
                shift_to(p, w, float(np.clip(baseline + delta, 0., 1.))) if delta else p.copy(),
                w, a, z, b, .1, True, i,
            )
            for name, delta in deltas.items()
        }
        # Current observed values enter the scorer only, then history for future dates.
        observed = outcome_groups[vote].reindex(v.municipality_id)
        y = v.yes_share.to_numpy(float)
        yes, no = observed.votes_yes.to_numpy(float), observed.votes_no.to_numpy(float)
        canton = observed.canton.astype(str).to_numpy()
        block = v[["vote_id", "municipality_id", "vote_date", "yes_share"]].copy()
        fold = "2016-18" if day.year <= 2018 else "2019-20" if day.year <= 2020 else "2021-22"
        for name, q in forecasts.items():
            m, c = multiscale(y, q, w, yes, no, canton)
            rows.append({"variant": name, "vote_id": vote, "vote_date": str(day.date()),
                         "fold": fold, "media_available": row is not None,
                         "correction_pp": 100 * deltas[name], **m})
            canton_rows.extend({"variant": name, "vote_id": vote, **r} for r in c)
            block[name] = q
        predictions.append(block)
        if row is not None:
            audit.append({"vote_id": vote, "vote_date": str(day.date()),
                          "prior_objects": sum(h[0] < day for h in history),
                          "prior_dates": len({h[0] for h in history if h[0] < day})})
            history.append((day, row, float(yes.sum() / (yes + no).sum()) - baseline))
    detail = pd.DataFrame(rows)
    summaries = []
    for name, group in detail.groupby("variant", sort=False):
        if len(group) != 66 or group.vote_date.nunique() != 23:
            raise ValueError("Incomplete result")
        covered = group[group.media_available]
        summaries.append({"variant": name, "objects": len(group),
                          "covered_objects": len(covered),
                          **{m: float(group[m].mean()) for m in METRICS},
                          **{"covered_" + m: float(covered[m].mean()) for m in METRICS},
                          "gain_interval": [0., 0.] if name == "reference" else
                          paired_date_bootstrap(detail, "reference", name)})
    if not np.isclose(summaries[0]["mae_pp"], REFERENCE, atol=.0002, rtol=0):
        raise ValueError("Reference did not reproduce")
    output.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output / "object_metrics.csv", index=False)
    detail.groupby(["variant", "fold"])[list(METRICS)].mean().to_csv(output / "fold_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    pd.DataFrame(audit).to_csv(output / "calibration.csv", index=False)
    pd.DataFrame(summaries).to_csv(output / "summary.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    manifest = {"status": "pilot_complete", "strict_forecast_ready": False,
                "media_source_sha256": sha(source), "same_date_excluded": True,
                "prediction_sha256": sha(output / "predictions.parquet"), "summary": summaries}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False))
    print("SUMMARY", json.dumps(summaries, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "acquisition", "fusion", "source", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    run(a.base, a.acquisition, a.fusion, a.source, a.output)


if __name__ == "__main__":
    main()
