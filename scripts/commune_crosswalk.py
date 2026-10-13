"""Map OFS commune codes from one date to another using the mutation history.

Inputs (written by download_commune_refs.py):
- data/raw/communes/mutations.csv : one row per (initial commune -> terminal commune) of each mutation
- data/raw/communes/snapshot_<date>.csv : communes valid at a date

A commune code at ``from_date`` is followed through every mutation dated after ``from_date``
and up to ``to_date`` (a snapshot at date D already contains the mutations dated D). Merges
(n -> 1) give one target. A split or a territory transfer (1 -> n) gives several targets, with
no weight: weights have to come from a population-like variable and are left to the caller.

Usage: python scripts/commune_crosswalk.py [--from 2010-01-01] [--to 2026-01-01]
Writes data/processed/crosswalk_<from>_to_<to>.csv and prints a validation report.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMUNES_DIR = ROOT / "data" / "raw" / "communes"
PROCESSED_DIR = ROOT / "data" / "processed"
COMMUNE_LEVEL = "3"  # snapshot levels: 1 canton, 2 district, 3 commune


def parse_fr_date(text: str) -> date:
    return datetime.strptime(text, "%d.%m.%Y").date()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_mutations(path: Path = COMMUNES_DIR / "mutations.csv") -> list[tuple[date, int, dict[str, set[str]]]]:
    """Return (date, mutation number, {initial code: {terminal codes}}) sorted chronologically."""
    events: dict[tuple[date, int], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in read_csv(path):
        key = (parse_fr_date(row["MutationDate"]), int(row["MutationNumber"]))
        events[key][row["InitialCode"]].add(row["TerminalCode"])
    return [(day, number, dict(rules)) for (day, number), rules in sorted(events.items())]


def load_snapshot_codes(day: date) -> dict[str, str]:
    """BFS code -> name of the communes (level 3) valid at the snapshot date."""
    name = f"snapshot_{day.isoformat()}.csv"
    path = COMMUNES_DIR / name
    rows = read_csv(path if path.exists() else COMMUNES_DIR / "vote_snapshots" / name)
    return {row["BfsCode"]: row["Name"] for row in rows if row["Level"] == COMMUNE_LEVEL}


def resolve(code: str, from_date: date, to_date: date, mutations) -> set[str]:
    """Codes at ``to_date`` that descend from commune ``code`` as it was at ``from_date``."""
    current = {code}
    for day, _number, rules in mutations:
        if day <= from_date:
            continue
        if day > to_date:
            break
        # Rules of one mutation read the state before the mutation, never their own output.
        updated = set()
        for item in current:
            updated |= rules.get(item, {item})
        current = updated
    return current


def classify(source: str, targets: set[str]) -> str:
    if len(targets) > 1:
        return "split"
    return "unchanged" if targets == {source} else "recoded_or_merged"


def build_crosswalk(from_date: date, to_date: date, mutations=None) -> list[dict]:
    mutations = mutations if mutations is not None else load_mutations()
    sources = load_snapshot_codes(from_date)
    rows = []
    for source, name in sources.items():
        targets = resolve(source, from_date, to_date, mutations)
        relation = classify(source, targets)
        for target in sorted(targets, key=int):
            rows.append({
                "source_code": source, "source_name": name, "from_date": from_date.isoformat(),
                "target_code": target, "to_date": to_date.isoformat(), "relation": relation,
                "n_targets": len(targets),
            })
    return rows


def validate(rows: list[dict], to_date: date) -> dict:
    valid_targets = load_snapshot_codes(to_date)
    unknown = sorted({r["target_code"] for r in rows if r["target_code"] not in valid_targets}, key=int)
    relations = defaultdict(set)
    for r in rows:
        relations[r["relation"]].add(r["source_code"])
    absorbed = defaultdict(set)
    for r in rows:
        absorbed[r["target_code"]].add(r["source_code"])
    return {
        "sources": len({r["source_code"] for r in rows}),
        "by_relation": {k: len(v) for k, v in relations.items()},
        "targets_not_in_target_snapshot": unknown,
        "target_communes_covered": len(absorbed),
        "target_communes_in_snapshot": len(valid_targets),
        "target_communes_without_source": sorted(set(valid_targets) - set(absorbed), key=int),
    }


def write_crosswalk(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="from_date", type=date.fromisoformat, default=date(2010, 1, 1))
    parser.add_argument("--to", dest="to_date", type=date.fromisoformat, default=date(2026, 1, 1))
    args = parser.parse_args()
    rows = build_crosswalk(args.from_date, args.to_date)
    out = PROCESSED_DIR / f"crosswalk_{args.from_date.isoformat()}_to_{args.to_date.isoformat()}.csv"
    write_crosswalk(rows, out)
    report = validate(rows, args.to_date)
    print(f"Wrote {out.relative_to(ROOT)} ({len(rows)} rows)")
    for key, value in report.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
