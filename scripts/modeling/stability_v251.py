"""Descriptive stability audit of pinned V24 out-of-fold object metrics; no fitting."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from datetime import date
from pathlib import Path

NAMES = ("reference", "v113_institution", "institution_replay", "scaled_squared", "scaled_huber")
METRICS = ("mae_pp", "centered_mae_pp", "national_mae_pp", "canton_mae_pp")
EXPECTED = {"reference": 7.229527497606816, "v113_institution": 6.955753873756506,
            "institution_replay": 6.955753873756503, "scaled_squared": 6.950427808889042,
            "scaled_huber": 7.012164999774358}


def read_panel(path: Path):
    panel = {name: {} for name in NAMES}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            day = date.fromisoformat(row["vote_date"])
            if not date(2016, 1, 1) <= day < date(2023, 1, 1):
                raise ValueError("Forbidden date")
            name = row["variant"]
            key = (day.isoformat(), row["vote_id"])
            if name not in panel or key in panel[name]:
                raise ValueError("Unknown variant or duplicate object")
            values = {m: float(row[m]) for m in METRICS}
            if not all(math.isfinite(x) and 0 <= x <= 100 for x in values.values()):
                raise ValueError("Invalid metrics")
            panel[name][key] = values
    keys = set(panel[NAMES[0]])
    if len(keys) != 66 or len({k[0] for k in keys}) != 23 or len({k[1] for k in keys}) != 66:
        raise ValueError("Population mismatch")
    if any(set(p) != keys for p in panel.values()):
        raise ValueError("Unpaired objects")
    for name, expected in EXPECTED.items():
        if not math.isclose(mean(panel[name], sorted(keys), "mae_pp"), expected, abs_tol=1e-8):
            raise ValueError("Pinned score mismatch")
    return panel


def mean(values, keys, metric):
    return math.fsum(values[k][metric] for k in keys) / len(keys)


def compare(panel, keys, excluded):
    kept = sorted(k for k in keys if k[0] not in excluded)
    scores = {n: {m: mean(p, kept, m) for m in METRICS} for n, p in panel.items()}
    return {"excluded_dates": list(excluded), "objects": len(kept), "scores": scores,
            "gain_scaled_vs_v113": scores["v113_institution"]["mae_pp"] - scores["scaled_squared"]["mae_pp"],
            "gain_huber_vs_scaled": scores["scaled_squared"]["mae_pp"] - scores["scaled_huber"]["mae_pp"]}


def bootstrap(panel, keys, control, candidate, seed=25, reps=10000):
    days = sorted({k[0] for k in keys})
    groups = [[k for k in sorted(keys) if k[0] == d] for d in days]
    sums = [math.fsum(panel[control][k]["mae_pp"] - panel[candidate][k]["mae_pp"] for k in g)
            for g in groups]
    rng = random.Random(seed)
    samples = []
    for _ in range(reps):
        ids = rng.choices(range(len(days)), k=len(days))
        samples.append(math.fsum(sums[i] for i in ids) / sum(len(groups[i]) for i in ids))
    samples.sort()
    return [samples[int(.025 * (reps - 1))], samples[int(.975 * (reps - 1))]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    panel = read_panel(args.input)
    keys = sorted(panel[NAMES[0]])
    days = sorted({k[0] for k in keys})
    result = {"status": "descriptive_only", "objects": len(keys), "dates": len(days),
              "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
              "full": compare(panel, keys, []),
              "leave_one_date": [compare(panel, keys, [d]) for d in days],
              "leave_three_consecutive_dates": [compare(panel, keys, days[i:i+3]) for i in range(len(days)-2)],
              "bootstrap_gain_scaled_vs_v113": bootstrap(panel, keys, "v113_institution", "scaled_squared"),
              "bootstrap_gain_huber_vs_scaled": bootstrap(panel, keys, "scaled_squared", "scaled_huber")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for group in ("leave_one_date", "leave_three_consecutive_dates"):
        gains = [r["gain_scaled_vs_v113"] for r in result[group]]
        print(group, len(gains), min(gains), max(gains), sum(g > 0 for g in gains))
    print("BOOTSTRAP", result["bootstrap_gain_scaled_vs_v113"], result["bootstrap_gain_huber_vs_scaled"])


if __name__ == "__main__":
    main()
