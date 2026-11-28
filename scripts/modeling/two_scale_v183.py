"""V18.3: separate between/within-canton contrast calibration on historical OOF forecasts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.modeling.affine_budget_v134 import EXPECTED_SHA
from scripts.modeling.canton_v105 import GEOGRAPHY, reference_cantons
from scripts.modeling.ensemble_v1010 import artifact_root, read_artifact
from scripts.modeling.error_budget_v133 import date_interval
from scripts.modeling.expectations_v101 import multiscale
from scripts.modeling.geographic_budget_v135 import match_scoring_geography
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import sha
from scripts.modeling.turnout_v103 import load_ballots

GRID = ((1., 1.), (1.25, .75), (.75, 1.25))
NAMES = ("reference", "between_up_within_down", "between_down_within_up")
BEST = 6.955753873756506
METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")


def amplitude(p, w, canton, scales):
    """Two disjoint weighted components; no observed results in this function."""
    p, w, canton = np.asarray(p, float), np.asarray(w, float), np.asarray(canton)
    if (p.shape != w.shape or p.shape != canton.shape or not np.isfinite(p).all()
            or not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0):
        raise ValueError("Invalid forecast inputs")
    if scales == (1., 1.):
        return p.copy()
    level = float(np.average(p, weights=w))
    group_mean = np.empty_like(p)
    for c in np.unique(canton):
        mask = canton == c
        if w[mask].sum() <= 0:
            raise ValueError("Canton without positive exposure")
        group_mean[mask] = np.average(p[mask], weights=w[mask])
    between, within = scales
    return shift_to(level + between * (group_mean - level)
                    + within * (p - group_mean), w, level)


def choose(history, day):
    previous = [loss for date, loss in history if date < day]
    if len(previous) < 4:
        return (1., 1.)
    # Dates equiponderated, objects equiponderated within each date.
    cost = np.mean(previous, axis=0) + .5 * np.square(np.asarray(GRID) - 1.).sum(axis=1)
    return GRID[int(np.argmin(cost))]


def self_test():
    p = np.array([.2, .4, .6, .8])
    w = np.array([1., 3., 2., 2.])
    c = np.array(["VD", "VD", "BE", "BE"])
    assert np.array_equal(amplitude(p, w, c, GRID[0]), p)
    for a in GRID:
        q = amplitude(p, w, c, a)
        assert np.all((q >= 0) & (q <= 1))
        assert abs(np.average(q - p, weights=w)) < 1e-9
    q = amplitude(p, w, c, GRID[1])
    assert np.isclose(q[1] - q[0], .75 * (p[1] - p[0]))
    assert np.isclose(np.average(q[2:], weights=w[2:]) - np.average(q[:2], weights=w[:2]),
                      1.25 * (np.average(p[2:], weights=w[2:]) - np.average(p[:2], weights=w[:2])))
    history = [(str(i), [5., 2., 7.]) for i in range(4)]
    assert choose(history, "3") == GRID[0]
    assert choose(history, "4") == GRID[1]
    assert choose(history + [("4", [0., 99., 0.])], "4") == GRID[1]
    print("SELF_TEST_OK", flush=True)


def run(source, output):
    root = artifact_root(source)
    if sha(root / "predictions.parquet") != EXPECTED_SHA:
        raise ValueError("Reference changed")
    frame = read_artifact(source, ["yes_share", "reference_weight", "institution_text"]).reset_index()
    geography = pd.read_parquet(GEOGRAPHY, columns=["municipality_id", "canton"])
    frame["forecast_canton"] = reference_cantons(geography, frame.municipality_id)
    frame = match_scoring_geography(frame, load_ballots())
    if not np.array_equal(frame.forecast_canton.to_numpy(), frame.canton.to_numpy()):
        raise ValueError("Independent geography differs from scoring geography")
    original = pd.read_csv(root / "object_metrics.csv", dtype={"vote_id": str})
    labels = original[original.variant.eq("institution_text")].set_index("vote_id", verify_integrity=True)
    history, rows, selection = [], [], []
    for day, block in frame.groupby("vote_date", sort=True):
        date = str(day.date())
        scale = choose(history, date)
        selection.append({"date": date, "prior_dates": len(history), "scale": scale})
        losses = []
        for vote, group in block.groupby("vote_id"):
            p, w = group.institution_text.to_numpy(), group.reference_weight.to_numpy()
            y = group.yes_share.to_numpy()
            forecasts = {a: amplitude(p, w, group.forecast_canton.to_numpy(), a) for a in GRID}
            # Historical losses become available only after the entire date is scored.
            losses.append([100 * float(np.mean(np.abs(y - forecasts[a]))) for a in GRID])
            label = labels.loc[vote]
            if pd.Timestamp(label.vote_date) != day:
                raise ValueError("Wrong object date")
            for name, a in (*zip(NAMES, GRID, strict=True), ("adaptive", scale)):
                met, _ = multiscale(y, forecasts[a], w, group.votes_yes, group.votes_no, group.canton)
                if name == "reference" and any(
                    abs(met[k] - label[k]) > 1e-8 for k in METRICS
                ):
                    raise ValueError("Original metric mismatch")
                rows.append({"variant": name, "vote_id": vote, "vote_date": date,
                             "fold": label["fold"], "domain": label["domain"], **met})
        history.append((date, np.mean(losses, axis=0)))
    detail = pd.DataFrame(rows)
    baseline = detail[detail.variant.eq("reference")].set_index("vote_id").mae_pp
    if len(baseline) != 66 or abs(baseline.mean() - BEST) > 1e-8:
        raise ValueError("Benchmark mismatch")
    summary = []
    for name, group in detail.groupby("variant", sort=False):
        if len(group) != 66 or group.vote_date.nunique() != 23:
            raise ValueError("Population mismatch")
        paired = group.assign(gain_pp=group.vote_id.map(baseline) - group.mae_pp)
        summary.append({"variant": name, **group[list(METRICS)].mean().to_dict(),
                        "gain_interval": date_interval(paired, "gain_pp", seed=183)})
    output.mkdir(parents=True, exist_ok=False)
    detail.to_csv(output / "object_metrics.csv", index=False)
    for column in ("fold", "domain"):
        detail.groupby(["variant", column])[list(METRICS)].agg(["mean", "size"]).to_csv(
            output / f"{column}_metrics.csv")
    result = {"status": "complete", "prediction_sha256": EXPECTED_SHA, "geography_sha256": sha(GEOGRAPHY),
              "rows": len(frame), "objects": 66, "dates": 23,
              "coverage": 1., "grid": GRID, "summary": summary, "selection": selection}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print("SUMMARY", json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    self_test()
    if not args.self_test:
        run(args.source, args.output)
