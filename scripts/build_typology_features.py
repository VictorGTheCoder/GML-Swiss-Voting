"""Build the commune territorial context table from the OFS typologies Excel export.

Input: data/raw/communes/typologies_2026-01-01.xlsx (written by download_commune_refs.py):
sheet "Données" with one row per commune of the 2026 register (two header rows and one row of
nomenclature identifiers), and one lookup sheet per nomenclature (code -> label).

Output: data/processed/commune_typologies.parquet, one row per commune (BFS code of the 2026
register, the geography of the vote cube) with codes and labels of
- urban_rural: typologie urbain-rural (3 classes)
- commune_type_9 / commune_type_25: typologie des communes
- language_region: région linguistique
The typology is static (a single vintage), so it is not a time-varying feature.

Usage: python scripts/build_typology_features.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from commune_crosswalk import load_snapshot_codes

ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data" / "raw" / "communes" / "typologies_2026-01-01.xlsx"
OUTPUT_PATH = ROOT / "data" / "processed" / "commune_typologies.parquet"
REFERENCE_DATE = date(2026, 1, 1)
DATA_SHEET = "Données"
NOMENCLATURE_ROW = 2  # identifiers such as CH1+CL_GDET9+2012.1, one per classified column

# Raw column position -> output name
COLUMNS = {
    0: "commune_code", 1: "commune_name", 3: "canton", 5: "district_name",
    6: "urban_rural", 7: "commune_type_9", 8: "commune_type_25", 9: "language_region",
}
CLASSIFIED = ["urban_rural", "commune_type_9", "commune_type_25", "language_region"]


def read_lookup(workbook: pd.ExcelFile, sheet: str) -> dict[str, str]:
    table = workbook.parse(sheet, header=None, skiprows=2, dtype=str)
    return dict(zip(table[0], table[1]))


def build() -> pd.DataFrame:
    workbook = pd.ExcelFile(INPUT_PATH)
    raw = workbook.parse(DATA_SHEET, header=None, dtype=str)
    nomenclature = {COLUMNS[i]: raw.iloc[NOMENCLATURE_ROW, i] for i in range(6, 10)}
    data = raw.iloc[NOMENCLATURE_ROW + 1:, list(COLUMNS)].rename(columns=COLUMNS).reset_index(drop=True)
    for column in CLASSIFIED:
        data[f"{column}_label"] = data[column].map(read_lookup(workbook, nomenclature[column]))
    data.attrs["nomenclatures"] = nomenclature
    return data


def check(table: pd.DataFrame) -> None:
    reference = load_snapshot_codes(REFERENCE_DATE)
    assert set(table["commune_code"]) == set(reference), "commune set differs from the register"
    assert table["commune_code"].is_unique, "duplicate commune"
    assert not table.isna().any().any(), "missing value or code without label"
    print(f"Checks passed: {len(table)} communes, nomenclatures {table.attrs['nomenclatures']}")


def main() -> None:
    table = build()
    check(table)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(OUTPUT_PATH, index=False)
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")
    for column in ["language_region_label", "urban_rural_label", "commune_type_9_label"]:
        print(table[column].value_counts().to_string(), "\n")


if __name__ == "__main__":
    main()
