"""Publish a compact evidence ledger after selection, comparison and final fit."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.municipal_v2 import digest, metrics, write_json

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def export(rounds, selected_output, destination):
    selected_output, destination = Path(selected_output), Path(destination)
    frozen = json.loads((selected_output / "frozen_selection.json").read_text())
    comparison = json.loads((selected_output / "comparison/summary.json").read_text())
    card = json.loads((selected_output / "candidate_model_card.json").read_text())
    manifest = json.loads((selected_output / "data_manifest.json").read_text())
    destination.mkdir(parents=True, exist_ok=True)
    records, flat = [], []
    for folder in rounds:
        folder = Path(folder)
        for path in sorted((folder / "trials").glob("*/trial.json")):
            record = json.loads(path.read_text())
            record["series"] = folder.name
            record["record_sha256"] = digest(path)
            records.append(record)
            row = {"series": folder.name, "run_id": record["run_id"],
                   "status": record["status"], "model": record["configuration"]["model"],
                   "blocks": record["configuration"].get("blocks", "base"),
                   "train_start": record["configuration"].get("train_start", "2012-01-01"),
                   "elapsed_seconds": record.get("elapsed_seconds"),
                   "configuration_json": json.dumps(record["configuration"], ensure_ascii=False, sort_keys=True),
                   "hypothesis": record.get("hypothesis", ""),
                   "error": record.get("error", ""),
                   **record.get("metrics", {})}
            for fold in record["folds"]:
                row[f"mae_{fold['name']}_pp"] = fold["metrics"]["macro_object_mae_pp"]
            flat.append(row)
    ledger = pd.DataFrame(flat).sort_values(["status", "macro_object_mae_pp", "run_id"])
    ledger.to_csv(destination / "experiments.csv", index=False)
    write_json(destination / "experiments.json", records)
    chosen = next(r for r in records if r["run_id"] == frozen["selected_run_id"]
                  and r["series"] == selected_output.name)
    windows = pd.DataFrame([{"window": f["name"], "train_objects": f["train_objects"],
                             "train_rows": f["train_rows"], **f["metrics"]} for f in chosen["folds"]])
    windows.to_csv(destination / "development_by_window.csv", index=False)
    for source, target in [("frozen_selection.json", "frozen_selection.json"),
                           ("candidate_model_card.json", "candidate_model_card.json"),
                           ("data_manifest.json", "data_manifest.json"),
                           ("comparison/summary.json", "comparison_summary.json"),
                           ("comparison/by_date.csv", "comparison_by_date.csv"),
                           ("comparison/by_canton.csv", "comparison_by_canton.csv")]:
        shutil.copyfile(selected_output / source, destination / target)

    data = pd.read_parquet(selected_output / "dataset.parquet",
                           columns=["municipality_id", "vote_id", "vote_key", "vote_date", "poll_available"])
    swiss = pd.read_parquet(ROOT / "data/processed/swissvotes/swissvotes_clean.parquet",
                            columns=["vote_key", "titel_off_f"])
    titles = data[["vote_id", "vote_key"]].drop_duplicates().merge(
        swiss, on="vote_key", how="left", validate="one_to_one").drop(columns="vote_key")
    titles["vote_id"] = titles.vote_id.astype(str)
    for source, target in [(selected_output / "trials" / chosen["run_id"] / "by_object.csv", "development_by_object.csv"),
                           (selected_output / "comparison/by_object.csv", "comparison_by_object.csv")]:
        objects = pd.read_csv(source, dtype={"vote_id": str})
        objects.merge(titles, on="vote_id", how="left", validate="one_to_one").to_csv(destination / target, index=False)

    predictions = pd.read_parquet(selected_output / "trials" / chosen["run_id"] / "predictions.parquet")
    covered = predictions.merge(data[["municipality_id", "vote_id", "poll_available"]],
                                on=["municipality_id", "vote_id"], how="left", validate="one_to_one")
    if covered.poll_available.isna().any():
        raise ValueError("Poll coverage missing for development rows")
    coverage_metrics = {name: metrics(covered.loc[covered.poll_available.eq(value)])[0]
                        for value, name in [(False, "unpolled"), (True, "polled")]
                        if covered.poll_available.eq(value).any()}
    _, by_object, _ = metrics(predictions)
    flags = covered.groupby("vote_id").poll_available.first()
    unpolled_objects = by_object.loc[~by_object.vote_id.map(flags).astype(bool)]
    floor = float(unpolled_objects.mae_pp.sum() / len(by_object))
    results = {
        "status_counts": ledger.status.value_counts().to_dict(), "total_trials": len(ledger),
        "selected_run_id": chosen["run_id"], "selected_configuration": chosen["configuration"],
        "development": chosen["metrics"], "development_coverage": coverage_metrics,
        "comparison": comparison, "candidate": card,
        "data": {k: manifest[k] for k in ["rows", "objects", "dates", "first_date", "last_date"]},
        "unchanged_unpolled_fallback_floor_pp": floor,
        "floor_scope": "For the chosen poll-anchor family with the same unpolled fallback: even zero error on every polled object cannot beat this overall MAE. Not a limit for other models or more data",
        "goal_reached_on_development": chosen["metrics"]["macro_object_mae_pp"] <= 4.,
        "independent_test_available": False, "strict_forecast_ready": False,
    }
    write_json(destination / "results.json", results)

    labels = [
        ("ridge_base_recent-", "Ridge · variables initiales"),
        ("xgboost_base_recent-", "XGBoost · variables initiales"),
        ("xgboost_political_recent-", "XGBoost · informations politiques"),
        ("xgboost_direction_recent-", "XGBoost · orientation des titres"),
        ("xgb_direction_k64-", "XGBoost · SelectKBest, k = 64"),
        ("catboost_political_recent-", "CatBoost · informations politiques"),
        ("profile_final_provenance-", "Profils communaux + XGBoost"),
        (chosen["run_id"], "Candidat avec sondages"),
    ]
    chart_rows = []
    for prefix, label in labels:
        candidates = ledger.loc[ledger.run_id.str.startswith(prefix) & ledger.status.eq("complete")]
        if candidates.empty:
            continue
        row = candidates.sort_values("macro_object_mae_pp").iloc[0]
        chart_rows.append({"label": label, "run_id": row.run_id, "mae_pp": row.macro_object_mae_pp})
    chart = pd.DataFrame(chart_rows)
    chart.to_csv(destination / "comparison_chart_data.csv", index=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    figure, axis = plt.subplots(figsize=(11.5, 6.8))
    colors = ["#9ba8b8"] * (len(chart) - 2) + ["#317b99", "#087f6e"]
    y = np.arange(len(chart))
    axis.barh(y, chart.mae_pp, color=colors, height=.63)
    axis.set_yticks(y, chart.label)
    axis.invert_yaxis()
    axis.axvline(4, color="#bd4536", linestyle="--", linewidth=1.5)
    axis.text(4.12, -.6, "Objectif : 4 points", color="#bd4536", fontsize=10)
    for position, value in zip(y, chart.mae_pp, strict=True):
        axis.text(value + .12, position, f"{value:.2f}".replace(".", ","), va="center", fontweight="bold")
    axis.set_xlim(0, max(15, chart.mae_pp.max() + 1.4))
    axis.set_xlabel("MAE moyenne par objet · points de pourcentage (plus bas = mieux)")
    axis.set_title("Votations suisses : les gains mesurés", loc="left", fontsize=18, fontweight="bold", pad=27)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.tick_params(axis="y", length=0)
    axis.xaxis.grid(True, alpha=.15)
    axis.set_axisbelow(True)
    figure.text(.025, .025, "Développement chronologique 2016–2022 · 66 objets · même population évaluée\n"
                "Sondages disponibles pour 24 objets ; repli structurel pour les 42 autres. Évaluation rétrospective.",
                fontsize=9, color="#4c5968")
    figure.tight_layout(rect=(0, .09, 1, 1))
    for suffix in ("png", "svg"):
        figure.savefig(destination / f"model_comparison.{suffix}", dpi=180, facecolor="white")
    plt.close(figure)
    print(json.dumps({"destination": str(destination), "total_trials": len(ledger),
                      "development_mae_pp": chosen["metrics"]["macro_object_mae_pp"],
                      "comparison_mae_pp": comparison["metrics"]["macro_object_mae_pp"],
                      "unchanged_fallback_floor_pp": floor}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=Path, nargs="+", default=[
        ROOT / "reports/generated/municipal_v2", ROOT / "reports/generated/municipal_v2_round2",
        ROOT / "reports/generated/municipal_v2_round3"])
    parser.add_argument("--selected-output", type=Path, default=ROOT / "reports/generated/municipal_v2_round3")
    parser.add_argument("--destination", type=Path, default=ROOT / "reports/datasets/municipal_v2_20261123")
    args = parser.parse_args()
    export(args.rounds, args.selected_output, args.destination)


if __name__ == "__main__":
    main()
