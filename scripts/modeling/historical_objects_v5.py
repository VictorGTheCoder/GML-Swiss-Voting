"""Audit-friendly chronological inventory of historical ballot objects.

Only metadata are read: the title comes from the Swissvotes snapshot and the
object ID/date from the V3 object table. No referendum outcomes are needed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scripts.common.config import ROOT

SWISS = ROOT / "data/processed/swissvotes/swissvotes_clean.parquet"
OBJECTS = ROOT / "data/processed/municipal_v3/object_features.csv"


def inventory(*, start_year=1990, end_year=2015):
    objects = pd.read_csv(
        OBJECTS, usecols=["vote_id", "vote_key", "vote_date"],
        dtype={"vote_id": str, "vote_key": str},
    )
    swiss = pd.read_parquet(SWISS)
    expected = {"vote_key", "vote_date", "titel_kurz_f", "titel_off_f", "rechtsform"}
    if not expected.issubset(swiss):
        raise ValueError(f"Missing Swissvotes title metadata: {sorted(expected - set(swiss))}")
    swiss = swiss[list(expected)].copy()
    swiss["vote_key"] = swiss.vote_key.astype(str)
    swiss["vote_date"] = pd.to_datetime(swiss.vote_date)
    if swiss.vote_key.duplicated().any():
        raise ValueError("Swissvotes vote_key repeated")
    objects["vote_date"] = pd.to_datetime(objects.vote_date)
    selected = objects[objects.vote_date.dt.year.between(start_year, end_year)]
    result = selected.merge(swiss, on="vote_key", how="left", validate="one_to_one", suffixes=("", "_swiss"))
    if len(result) != len(selected) or result.titel_off_f.isna().any():
        raise ValueError("Incomplete Swissvotes title join")
    if not result.vote_date.eq(result.vote_date_swiss).all():
        raise ValueError("Mismatched vote-date identifiers")
    result = result[[
        "vote_id", "vote_key", "vote_date", "rechtsform", "titel_kurz_f", "titel_off_f",
    ]].sort_values(["vote_date", "vote_id"])
    if result.vote_id.duplicated().any():
        raise ValueError("Duplicate referendum IDs")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2015)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    frame = inventory(start_year=args.start_year, end_year=args.end_year)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise FileExistsError("Do not overwrite inventory snapshot")
        frame.to_csv(args.output, index=False)
    for row in frame.itertuples(index=False):
        title = str(row.titel_kurz_f) if pd.notna(row.titel_kurz_f) else str(row.titel_off_f)
        print(f"{row.vote_date.date()} | {row.vote_id} | {row.rechtsform} | {title}", flush=True)
    print(f"HISTORIC INVENTORY: {len(frame)} voting objects", flush=True)


if __name__ == "__main__":
    main()
