"""Convert the raw Répertoire des communes CSV files to typed Parquet files in data/interim/repertoire_communes/.

data/raw/repertoire_communes/ keeps the files exactly as downloaded; this step only changes the storage
format and types, no value is altered.

- commune_mutations.parquet: mutation history, dates as datetime.
- commune_snapshots.parquet: register snapshots (all levels) of the reference dates and of every
  vote date, with a snapshot_date column.

Usage: python -m scripts.repertoire_communes.convert_repertoire_to_parquet
"""

from __future__ import annotations

import re

import pandas as pd

from scripts.common.communes import REGISTER_INTERIM_DIR, REGISTER_RAW_DIR, ROOT


def convert_mutations() -> pd.DataFrame:
    table = pd.read_csv(REGISTER_RAW_DIR / "mutations.csv", encoding="utf-8-sig", dtype=str)
    table["MutationDate"] = pd.to_datetime(table["MutationDate"], format="%d.%m.%Y")
    for column in ("MutationNumber", "InitialStep", "TerminalStep"):
        table[column] = table[column].astype("int32")
    return table


def convert_snapshots() -> pd.DataFrame:
    paths = list(REGISTER_RAW_DIR.glob("snapshot_*.csv")) + list((REGISTER_RAW_DIR / "vote_snapshots").glob("snapshot_*.csv"))
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
    REGISTER_INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    for name, build in (("commune_mutations", convert_mutations), ("commune_snapshots", convert_snapshots)):
        table = build()
        path = REGISTER_INTERIM_DIR / f"{name}.parquet"
        table.to_parquet(path, index=False)
        print(f"Wrote {path.relative_to(ROOT)}: {len(table):,} rows, {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
