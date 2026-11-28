"""V20.2: contextual transfer of prior-date aggregate residuals."""
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
from scripts.modeling.residual_intercepts_v201 import date_residuals
from scripts.modeling.semantic_poll_comparison_v4 import sha
from scripts.modeling.turnout_v103 import load_ballots

BEST = 6.955753873756506
METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")


def signature(p, w, canton):
    """Forecast-only canton shape; no target outcomes."""
    frame = pd.DataFrame({"p": p, "w": w, "c": canton})
    frame["pw"] = frame.p * frame.w
    sums = frame.groupby("c")[["pw", "w"]].sum()
    if (sums.w <= 0).any():
        raise ValueError("Nonpositive canton forecast weights")
    x = sums.pw / sums.w
    x -= x.mean()
    norm = np.linalg.norm(x)
    return x / norm if norm > 1e-12 else x * 0.


def similarity(a, b):
    if not a.index.equals(b.index) or min(np.linalg.norm(a), np.linalg.norm(b)) < 1e-12:
        return 1.
    cosine = float(np.clip(a @ b, -1., 1.))
    return ((1. + cosine) / 2.) ** 2


def history_vector(history, day, keys, target, weighted):
    """Equal prior-date weight for uniform; contextual kernel for comparison."""
    previous = [(date, entries) for date, entries in history if date < day]
    if len(previous) < 4:
        return np.zeros(len(keys))
    date_values, date_weights = [], []
    for _, entries in previous:
        weights = np.array([similarity(target, x[0]) if weighted else 1. for x in entries])
        date_weights.append(float(weights.mean()))
        if weights.sum() <= 1e-12:
            weights = np.ones(len(entries))
        table = pd.concat([x[1] for x in entries], axis=1)
        values = table.mul(weights, axis=1).sum(axis=1)
        den = table.notna().mul(weights, axis=1).sum(axis=1)
        date_values.append(values / den.replace(0., np.nan))
    dw = np.array(date_weights)
    if dw.sum() <= 1e-12:
        dw = np.ones(len(previous))
    dw *= len(previous) / dw.sum()
    table = pd.concat(date_values, axis=1)
    estimate = table.mul(dw, axis=1).sum(axis=1) / (
        table.notna().mul(dw, axis=1).sum(axis=1) + 5.)
    return estimate.reindex(keys, fill_value=0.).to_numpy(float)


def forecasts(p, w, history, day, canton):
    target = signature(p, w, canton)
    level = np.average(p, weights=w)
    return {
        "reference": p.copy(),
        "canton_uniform": shift_to(p + history_vector(history, day, canton, target, False), w, level),
        "canton_similarity": shift_to(p + history_vector(history, day, canton, target, True), w, level),
    }


def self_test():
    c = np.array(["BE", "BE", "VD", "VD"])
    p = np.array([.3, .4, .6, .7])
    w = np.array([1., 2., 3., 4.])
    a = signature(p, w, c)
    b = signature(1. - p, w, c)
    z = signature(np.full(4, .5), w, c)
    assert np.isclose(similarity(a, a), 1.)
    assert np.isclose(similarity(a, b), 0.)
    assert similarity(a, z) == 1.
    assert similarity(a, a.iloc[:1]) == 1.
    ra = pd.Series({"BE": .1, "VD": -.1})
    rb = -ra
    history = [(str(i), [(a, ra), (b, rb)]) for i in range(4)]
    assert np.array_equal(history_vector(history, "3", c, a, True), np.zeros(4))
    assert np.allclose(history_vector(history, "4", c, a, False), 0.)
    expected = np.array([.1, .1, -.1, -.1]) * 4 / 9
    assert np.allclose(history_vector(history, "4", c, a, True), expected)
    assert np.allclose(history_vector(history + [("4", [(b, rb)])], "4", c, a, True), expected)
    assert history_vector(history, "4", ["missing"], a, True)[0] == 0.
    opposite = [(str(i), [(b, rb)]) for i in range(4)]
    assert np.allclose(history_vector(opposite, "4", c, a, True),
                       history_vector(opposite, "4", c, a, False))
    for q in forecasts(p, w, history, "4", c).values():
        assert np.all((q >= 0) & (q <= 1))
        assert np.isclose(np.average(q, weights=w), np.average(p, weights=w), atol=1e-9)
    print("SELF_TEST_OK", flush=True)


def run(source, output):
    root = artifact_root(source)
    if sha(root / "predictions.parquet") != EXPECTED_SHA:
        raise ValueError("Reference changed")
    frame = read_artifact(source, ["yes_share", "reference_weight", "institution_text"]).reset_index()
    geo = pd.read_parquet(GEOGRAPHY, columns=["municipality_id", "canton"])
    frame["forecast_canton"] = reference_cantons(geo, frame.municipality_id)
    frame = match_scoring_geography(frame, load_ballots())
    if not np.array_equal(frame.forecast_canton.to_numpy(), frame.canton.to_numpy()):
        raise ValueError("Geography mismatch")
    original = pd.read_csv(root / "object_metrics.csv", dtype={"vote_id": str})
    labels = original[original.variant.eq("institution_text")].set_index("vote_id", verify_integrity=True)
    history, rows, canton_rows, municipal_rows = [], [], [], []
    for day, block in frame.groupby("vote_date", sort=True):
        date = str(day.date())
        pending = []
        for vote, g in block.groupby("vote_id"):
            p, w = g.institution_text.to_numpy(), g.reference_weight.to_numpy()
            pred = forecasts(p, w, history, date, g.forecast_canton.to_numpy())
            y = g.yes_share.to_numpy()
            label = labels.loc[vote]
            if pd.Timestamp(label.vote_date) != day:
                raise ValueError("Wrong object date")
            for name, q in pred.items():
                met, cs = multiscale(y, q, w, g.votes_yes, g.votes_no, g.canton)
                if name == "reference" and any(abs(met[k] - label[k]) > 1e-8 for k in METRICS):
                    raise ValueError("Original metric mismatch")
                rows.append({"variant": name, "vote_id": vote, "vote_date": date,
                             "prior_dates": len(history), "fold": label["fold"],
                             "domain": label["domain"], **met})
                canton_rows.extend({"variant": name, "vote_id": vote, **c} for c in cs)
                municipal_rows.append(pd.DataFrame({"variant": name, "municipality_id": g.municipality_id,
                                                    "absolute_error_pp": 100 * np.abs(q - y)}))
            pending.append((signature(p, w, g.forecast_canton.to_numpy()), date_residuals(g)["canton"]))
        history.append((date, pending))
    detail = pd.DataFrame(rows)
    baseline = detail[detail.variant.eq("reference")].set_index("vote_id").mae_pp
    if len(baseline) != 66 or abs(baseline.mean() - BEST) > 1e-8:
        raise ValueError("Benchmark mismatch")
    uniform = detail[detail.variant.eq("canton_uniform")].mae_pp.mean()
    if abs(uniform - 6.980529312872354) > 1e-8:
        raise ValueError("V20.1 uniform comparison mismatch")
    summary = []
    for name, group in detail.groupby("variant", sort=False):
        if len(group) != 66 or group.vote_date.nunique() != 23:
            raise ValueError("Population mismatch")
        paired = group.assign(gain_pp=group.vote_id.map(baseline) - group.mae_pp)
        summary.append({"variant": name, **group[list(METRICS)].mean().to_dict(),
                        "gain_interval": date_interval(paired, "gain_pp", seed=202),
                        "active_objects": int(group.prior_dates.ge(4).sum()) if name != "reference" else 0})
    output.mkdir(parents=True, exist_ok=False)
    detail.to_csv(output / "object_metrics.csv", index=False)
    for col in ("fold", "domain", "vote_date"):
        detail.groupby(["variant", col])[list(METRICS)].agg(["mean", "size"]).to_csv(output / f"{col}_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output / "canton_metrics.csv", index=False)
    pd.concat(municipal_rows).groupby(["variant", "municipality_id"]).absolute_error_pp.agg(
        ["mean", "size"]).to_csv(output / "municipality_metrics.csv")
    result = {"status": "complete", "prediction_sha256": EXPECTED_SHA, "geography_sha256": sha(GEOGRAPHY),
              "rows": len(frame), "objects": 66, "dates": 23, "coverage": 1.,
              "prior_pseudo_dates": 5, "warmup_dates": 4, "summary": summary}
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
