"""V20.1: strictly prior-date residual intercepts on frozen aggregate forecasts."""
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

BEST = 6.955753873756506
METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")
NAMES = ("reference", "canton_intercept", "municipality_intercept", "hierarchical")


def history_vector(history, day, keys, column):
    """One mean per completed date and key; five zero pseudo-dates."""
    previous = [x[column] for date, x in history if date < day]
    if len(previous) < 4:
        return np.zeros(len(keys))
    table = pd.concat(previous, axis=1)
    estimate = table.sum(axis=1) / (table.count(axis=1) + 5.)
    return estimate.reindex(keys, fill_value=0.).to_numpy(float)


def date_residuals(block):
    """Remove object mean, then split canton and within-canton signed error."""
    b = block.copy()
    b["residual"] = b.yes_share - b.institution_text
    b["residual"] -= b.groupby("vote_id").residual.transform("mean")
    b["between"] = b.groupby(["vote_id", "forecast_canton"]).residual.transform("mean")
    b["within"] = b.residual - b.between
    return {
        "canton": b.groupby(["vote_id", "forecast_canton"]).between.first()
        .groupby("forecast_canton").mean(),
        "municipal": b.groupby("municipality_id").residual.mean(),
        "within": b.groupby("municipality_id").within.mean(),
    }


def forecasts(p, w, history, day, municipality, canton):
    c = history_vector(history, day, canton, "canton")
    m = history_vector(history, day, municipality, "municipal")
    u = history_vector(history, day, municipality, "within")
    level = np.average(p, weights=w)
    return {
        "reference": p.copy(),
        "canton_intercept": shift_to(p + c, w, level),
        "municipality_intercept": shift_to(p + m, w, level),
        "hierarchical": shift_to(p + c + u, w, level),
    }


def self_test():
    b = pd.DataFrame({"vote_id": ["a"] * 4, "municipality_id": ["1", "2", "3", "4"],
                      "forecast_canton": ["VD", "VD", "BE", "BE"],
                      "yes_share": [.4, .5, .6, .7], "institution_text": [.3, .3, .7, .7]})
    r = date_residuals(b)
    assert np.isclose(r["within"].loc["1"] + r["within"].loc["2"], 0.)
    history = [(str(i), r) for i in range(4)]
    assert np.array_equal(history_vector(history, "3", ["1"], "municipal"), [0.])
    assert np.isclose(history_vector(history, "4", ["1"], "municipal")[0],
                      4 * r["municipal"].loc["1"] / 9)
    assert history_vector(history, "4", ["missing"], "municipal")[0] == 0
    assert np.array_equal(history_vector(history, "4", ["1"], "municipal"),
                          history_vector(history + [("4", r)], "4", ["1"], "municipal"))
    p = b.institution_text.to_numpy()
    w = np.array([1., 3., 2., 4.])
    out = forecasts(p, w, history, "4", b.municipality_id, b.forecast_canton)
    for q in out.values():
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
        for vote, g in block.groupby("vote_id"):
            p, w = g.institution_text.to_numpy(), g.reference_weight.to_numpy()
            pred = forecasts(p, w, history, date, g.municipality_id, g.forecast_canton)
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
        history.append((date, date_residuals(block)))
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
                        "gain_interval": date_interval(paired, "gain_pp", seed=201),
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
