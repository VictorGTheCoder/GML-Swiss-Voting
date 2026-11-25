"""Audit reviewed national poll candidates; no election results or model inputs."""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from scripts.modeling.aps_audit_v131 import roster

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ROOT / "data/external/polls_v132/candidates.csv"
REFERENCE = ROOT / "data/external/polls_v81/leewas_latest_2016_2022.csv"
ROSTER = ROOT / "data/processed/municipal_v3/object_features.csv"


def audit(candidates, reference, expected):
    seen = set()
    waves = {}
    latest = 0
    agrees = 0
    early = 0
    dates = set()
    for row in candidates:
        key = row["vote_key"]
        vote = date.fromisoformat(row["vote_date"])
        start = date.fromisoformat(row["fieldwork_start"])
        end = date.fromisoformat(row["fieldwork_end"])
        release = date.fromisoformat(row["stated_release_date"])
        wave = int(row["wave"])
        yes = float(row["yes_share_pp"])
        identity = (key, wave)
        if (expected.get(key) != vote or identity in seen or wave < 1
                or not start <= end <= release < vote or not 0 <= yes <= 100):
            raise ValueError("Invalid candidate identity, timing or share")
        seen.add(identity)
        waves.setdefault(key, []).append((wave, start, end, release, vote))
        dates.add(vote)
        role = row["comparison_role"]
        if role == "latest_candidate":
            latest += 1
            agrees += int(yes == reference[key])
        elif role == "early_wave":
            early += 1
        else:
            raise ValueError("Unknown comparison role")
    for observations in waves.values():
        ordered = sorted(observations)
        for previous, current in zip(ordered, ordered[1:]):
            if not previous[2] < current[1] or not previous[3] < current[3]:
                raise ValueError("Overlapping or reversed survey waves")
    multiwave = [values for values in waves.values() if len(values) >= 2]
    return {"rows": len(seen), "objects": len(waves), "dates": len(dates),
            "multiwave_objects": len(multiwave),
            "three_wave_objects": sum(len(values) == 3 for values in waves.values()),
            "multiwave_dates": len({values[0][4] for values in multiwave}),
            "latest_candidates": latest, "latest_agreements": agrees,
            "early_waves": early, "training_rows_admitted": 0,
            "strict_forecast_ready": False}


def main():
    expected = roster(ROSTER)
    with REFERENCE.open(encoding="utf-8", newline="") as source:
        reference = {row["vote_key"]: float(row["tamedia_yes"])
                     for row in csv.DictReader(source)}
    with CANDIDATES.open(encoding="utf-8", newline="") as source:
        print(json.dumps(audit(csv.DictReader(source), reference, expected)))


if __name__ == "__main__":
    main()
