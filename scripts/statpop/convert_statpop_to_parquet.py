"""Convert the raw STATPOP CSV files to a typed Parquet file in data/interim/statpop/.

data/raw/statpop/ keeps the files exactly as downloaded; this step only changes the storage
format and types, no value is altered.

statpop.parquet has one row per (year, commune code, nationality), counts by single year of age
(age_0 ... age_100, the last one being "100 ans ou plus") and the total. Codes are those of the
2025 boundaries used by the STATPOP files.

Usage: python -m scripts.statpop.convert_statpop_to_parquet
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.common.communes import ROOT, STATPOP_INTERIM_DIR, STATPOP_RAW_DIR

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
    frames = [statpop_year(path) for path in sorted(STATPOP_RAW_DIR.glob("statpop_*.csv"))]
    table = pd.concat(frames, ignore_index=True)
    if not (table[AGE_COLUMNS].sum(axis=1) == table["total"]).all():
        raise ValueError("single-year ages do not add up to the total")
    return table


def main() -> None:
    STATPOP_INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    table = convert_statpop()
    path = STATPOP_INTERIM_DIR / "statpop.parquet"
    table.to_parquet(path, index=False)
    print(f"Wrote {path.relative_to(ROOT)}: {len(table):,} rows, {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
