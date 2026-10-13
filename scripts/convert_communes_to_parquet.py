"""Convert the raw commune reference downloads to typed Parquet files in data/interim/.

data/raw/ keeps the files exactly as downloaded (see data/raw/communes/provenance.json);
this step only changes the storage format and types, no value is altered.

- statpop.parquet: one row per (year, commune code, nationality), counts by single year of age
  (age_0 ... age_100, the last one being "100 ans ou plus") and the total; codes are those of
  the 2025 boundaries used by the STATPOP files.
- commune_mutations.parquet: mutation history, dates as datetime.
- commune_snapshots.parquet: register snapshots (all levels) of the reference dates and of every
  vote date, with a snapshot_date column.

Usage: python scripts/convert_communes_to_parquet.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COMMUNES_DIR = ROOT / "data" / "raw" / "communes"
STATPOP_DIR = ROOT / "data" / "raw" / "statpop"
INTERIM_DIR = ROOT / "data" / "interim"

AGE_COLUMNS = [f"age_{age}" for age in range(101)]
NATIONALITIES = {"Suisse": "swiss"}  # anything else is "foreign"; the total row starts with "Nationalit"


def nationality_key(label: str) -> str:
    if label.startswith("Nationalit"):
        return "total"
    return NATIONALITIES.get(label, "foreign")


def statpop_year(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, encoding="utf-8", dtype=str)
    place = raw.iloc[:, 1].str.extract(r"^\.+(\d+) (.*)$")
    if place.isna().any().any():
        raise ValueError(f"{path.name}: rows that are not communes")
    frame = pd.DataFrame({
        "year": raw.iloc[:, 0].astype("int16"),
        "commune_code": place[0].str.lstrip("0"),
        "commune_name": place[1],
        "nationality": raw.iloc[:, 3].map(nationality_key),
        "total": pd.to_numeric(raw.iloc[:, 5]).astype("int32"),
    })
    ages = raw.iloc[:, 6:].apply(pd.to_numeric).astype("int32")
    ages.columns = AGE_COLUMNS
    return pd.concat([frame, ages], axis=1)


def convert_statpop() -> pd.DataFrame:
    frames = [statpop_year(path) for path in sorted(STATPOP_DIR.glob("statpop_*.csv"))]
    table = pd.concat(frames, ignore_index=True)
    if not (table[AGE_COLUMNS].sum(axis=1) == table["total"]).all():
        raise ValueError("single-year ages do not add up to the total")
    return table


def convert_mutations() -> pd.DataFrame:
    table = pd.read_csv(COMMUNES_DIR / "mutations.csv", encoding="utf-8-sig", dtype=str)
    table["MutationDate"] = pd.to_datetime(table["MutationDate"], format="%d.%m.%Y")
    for column in ("MutationNumber", "InitialStep", "TerminalStep"):
        table[column] = table[column].astype("int32")
    return table


def convert_snapshots() -> pd.DataFrame:
    paths = list(COMMUNES_DIR.glob("snapshot_*.csv")) + list((COMMUNES_DIR / "vote_snapshots").glob("snapshot_*.csv"))
    frames = []
    for path in sorted(paths, key=lambda p: p.stem):
        frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
        frame.insert(0, "snapshot_date", pd.Timestamp(re.search(r"\d{4}-\d{2}-\d{2}", path.stem).group()))
        frames.append(frame)
    table = pd.concat(frames, ignore_index=True).drop_duplicates()
    for column in ("ValidFrom", "ValidTo"):
        table[column] = pd.to_datetime(table[column], format="%d.%m.%Y")
    table["Level"] = table["Level"].astype("int8")
    return table


def main() -> None:
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    for name, build in (("statpop", convert_statpop), ("commune_mutations", convert_mutations),
                        ("commune_snapshots", convert_snapshots)):
        table = build()
        path = INTERIM_DIR / f"{name}.parquet"
        table.to_parquet(path, index=False)
        print(f"Wrote {path.relative_to(ROOT)}: {len(table):,} rows, {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
