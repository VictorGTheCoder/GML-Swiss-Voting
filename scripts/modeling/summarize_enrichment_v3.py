"""Export the small V3 evidence tables and paired voting-date uncertainty."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.modeling.municipal_v2 import write_json


def paired_interval(candidate, reference, label):
    if (candidate.vote_id.duplicated().any() or reference.vote_id.duplicated().any()
            or set(candidate.vote_id) != set(reference.vote_id)):
        raise ValueError("Matched comparisons require identical unique object populations")
    joined = candidate[["vote_id", "vote_date", "mae_pp"]].merge(
        reference[["vote_id", "vote_date", "mae_pp"]], on="vote_id", validate="one_to_one",
        suffixes=("_candidate", "_reference"))
    if not joined.vote_date_candidate.equals(joined.vote_date_reference):
        raise ValueError("Voting dates disagree")
    joined["difference"] = joined.mae_pp_candidate - joined.mae_pp_reference
    groups = joined.groupby("vote_date_candidate").difference.agg(["sum", "count"])
    rng = np.random.default_rng(20261123)
    draws = rng.integers(0, len(groups), (4000, len(groups)))
    delta = groups["sum"].to_numpy()[draws].sum(1) / groups["count"].to_numpy()[draws].sum(1)
    return {"comparison": label, "difference_pp": float(joined.difference.mean()),
            "lower_95_pp": float(np.quantile(delta, .025)), "upper_95_pp": float(np.quantile(delta, .975)),
            "dates": len(groups), "objects": len(joined), "replicates": len(delta),
            "unit": "whole voting date",
            "interpretation": "descriptive paired bootstrap; exploratory reused development, no multiplicity or selection correction"}


def summarize(campaign_dir, polls_dir, output, interrupted=None):
    output.mkdir(parents=True, exist_ok=True)
    if (output / "results.json").exists():
        raise FileExistsError("Preserve the previous report; choose a new output directory")
    campaign = json.loads((campaign_dir / "campaign.json").read_text())
    polling = json.loads((polls_dir / "polling_comparison.json").read_text())
    if campaign["status"] != "complete" or polling["status"] != "complete":
        raise ValueError("Do not summarize an incomplete final campaign")
    copies = [(campaign_dir / "campaign.json", "structural_campaign.json"),
              (polls_dir / "polling_comparison.json", "polling_comparison.json"),
              (polls_dir / "polling_by_object.csv", "polling_by_object.csv")]
    for source, name in copies:
        (output / name).write_bytes(source.read_bytes())
    rows = []
    for run in campaign["runs"]:
        name = run["name"]
        rows.append({"name": name, "structural_mae_pp": run["metrics"]["macro_object_mae_pp"],
                     "current_polls_trend_mae_pp": run["current_poll_metrics"]["macro_object_mae_pp"],
                     "oracle_local_mae_pp": run["oracle_offset_mae_pp"], "seconds": run["elapsed_seconds"]})
        for suffix in ("by_object.csv", "by_date.csv", "diagnostics.csv"):
            source = campaign_dir / (name + "_" + suffix)
            (output / source.name).write_bytes(source.read_bytes())
    pd.DataFrame(rows).to_csv(output / "structural_comparison.csv", index=False)
    baseline = pd.read_csv(campaign_dir / "baseline_pca5_by_object.csv", dtype={"vote_id": str})
    intervals = [paired_interval(
        pd.read_csv(campaign_dir / (row["name"] + "_by_object.csv"), dtype={"vote_id": str}),
        baseline, row["name"] + " minus baseline structural") for row in rows[1:]]
    poll_objects = pd.read_csv(polls_dir / "polling_by_object.csv", dtype={"vote_id": str})
    original = poll_objects[poll_objects.name.eq("baseline_original_trend")]
    for name in ("baseline_expanded_trend", "baseline_expanded_latest"):
        intervals.append(paired_interval(poll_objects[poll_objects.name.eq(name)], original,
                                         name + " minus original trend"))
    replay = []
    if interrupted is not None:
        initial = json.loads(interrupted.read_text())
        (output / "interrupted_campaign.json").write_bytes(interrupted.read_bytes())
        for run in initial["runs"]:
            final = next(r for r in campaign["runs"] if r["name"] == run["name"])
            replay.append({"name": run["name"],
                           "predictions_identical": run["predictions_sha256"] == final["predictions_sha256"],
                           "same_configuration": run["configuration"] == final["configuration"]})
    # Coverage is measured from the collected source and the matched evaluation.
    source_audit = polling["source_audit"]
    summary = {"structural": rows, "polling": polling["runs"], "paired_date_bootstrap": intervals,
               "interrupted_run_replay": replay, "new_objects": 24, "new_poll_rows": polling["historical_poll_rows"],
               "development_objects": len(baseline), "polled_before": polling["runs"][0]["polled_objects"],
               "polled_after": next(r["polled_objects"] for r in polling["runs"] if r["collection"] == "expanded"),
               "new_object_features": 32, "goal_mae_pp": 4,
               "goal_reached": any(r["metrics"]["macro_object_mae_pp"] <= 4 for r in polling["runs"]),
               "comparison_2023_onward_rerun": False, "frozen_v2_replaced": False,
               "strict_forecast_ready": source_audit["strict_forecast_ready"]}
    write_json(output / "results.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--polls", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interrupted", type=Path)
    args = parser.parse_args()
    summarize(args.campaign, args.polls, args.output, args.interrupted)


if __name__ == "__main__":
    main()
