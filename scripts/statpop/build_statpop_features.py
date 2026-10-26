"""Build commune demographic features from the STATPOP files (data/raw/statpop/).

STATPOP years 2010-2025 are expressed on the 2025 commune boundaries. Codes are moved to the
reference geography (the register at 2026-01-01, the one the vote cube follows) with
commune_crosswalk.resolve(), and counts are summed before shares are computed.

One row per (commune, year): permanent resident population, foreign share, age-group shares and
mean age. ``available_from`` is the date from which a year may be used for a vote. OFS publishes the
definitive commune-level results of year Y in late August of year Y + 1 (observed in the BFS
catalogue: 2019 on 2020-08-27, 2020 on 2021-09-01, 2021 on 2022-08-25, 2022 on 2023-08-24,
2023 on 2024-08-22, 2024 on 2025-08-27, 2025 on 2026-08-20). Only canton-level provisional
results come out earlier (early April), so they are not used. The rule below applies the
latest observed day plus one to every year; earlier years (2010-2018) are assumed to follow
the same calendar. The files hold the vintage of 2026-08-20, in which earlier years may have
been revised after their first publication.

Usage: python -m scripts.statpop.build_statpop_features
Writes data/processed/statpop/statpop_features.parquet
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.communes import ROOT, STATPOP_PROCESSED_DIR
from scripts.common.communes import STATPOP_RAW_DIR as RAW_DIR
from scripts.repertoire_communes.commune_crosswalk import (
    load_mutations,
    load_snapshot_codes,
    resolve,
)

OUTPUT_PATH = STATPOP_PROCESSED_DIR / "statpop_features.parquet"

REFERENCE_DATE = date(2026, 1, 1)
STATPOP_GEOGRAPHY_DATE = date(2025, 12, 31)  # last boundaries of the STATPOP files
AVAILABLE_MONTH_DAY = (9, 2)  # data of year Y usable from 2 September of year Y + 1

COL_COMMUNE, COL_NATIONALITY, COL_TOTAL, FIRST_AGE_COL = 1, 3, 5, 6  # positions in the raw CSV
AGE_GROUPS = {"0_19": (0, 19), "20_39": (20, 39), "40_64": (40, 64), "65_plus": (65, 100)}


def nationality_key(label: str) -> str:
    if label.startswith("Nationalit"):
        return "total"
    return "swiss" if label == "Suisse" else "foreign"


def read_year(path: Path) -> pd.DataFrame:
    """Wide raw file -> one row per (commune code, nationality) with the 101 single-year ages."""
    raw = pd.read_csv(path, encoding="utf-8", dtype=str)
    codes = raw.iloc[:, COL_COMMUNE].str.extract(r"^\.+(\d+) ")[0]
    if codes.isna().any():
        raise ValueError(f"{path.name}: rows that are not communes")
    frame = raw.iloc[:, [COL_TOTAL] + list(range(FIRST_AGE_COL, raw.shape[1]))].apply(pd.to_numeric)
    frame.columns = ["total"] + list(range(101))  # last column is '100 ans ou plus'
    frame.insert(0, "nationality", raw.iloc[:, COL_NATIONALITY].map(nationality_key))
    frame.insert(0, "code", codes.str.lstrip("0"))
    frame.insert(0, "year", int(raw.iloc[0, 0]))
    return frame


def to_reference_codes(codes: pd.Series, mutations) -> pd.Series:
    targets = {code: resolve(code, STATPOP_GEOGRAPHY_DATE, REFERENCE_DATE, mutations) for code in codes.unique()}
    multiple = {code: t for code, t in targets.items() if len(t) != 1}
    if multiple:
        raise ValueError(f"Commune split, needs weights: {multiple}")
    return codes.map({code: next(iter(t)) for code, t in targets.items()})


def build() -> pd.DataFrame:
    files = sorted(RAW_DIR.glob("statpop_*.csv"))
    long = pd.concat([read_year(path) for path in files], ignore_index=True)
    long["code"] = to_reference_codes(long["code"], load_mutations())
    age_columns = list(range(101))
    summed = long.groupby(["year", "code", "nationality"], as_index=False)[["total"] + age_columns].sum()

    all_nat = summed[summed["nationality"] == "total"].set_index(["year", "code"])
    foreign = summed[summed["nationality"] == "foreign"].set_index(["year", "code"])["total"]
    features = pd.DataFrame({"pop_total": all_nat["total"], "pop_foreign": foreign})
    ages = all_nat[age_columns].to_numpy()
    for name, (low, high) in AGE_GROUPS.items():
        features[f"pop_{name}"] = ages[:, low:high + 1].sum(axis=1)
    features["pop_80_plus"] = ages[:, 80:].sum(axis=1)
    features["mean_age"] = (ages * np.arange(101)).sum(axis=1) / ages.sum(axis=1)
    features["share_foreign"] = features["pop_foreign"] / features["pop_total"]
    for name in list(AGE_GROUPS) + ["80_plus"]:
        features[f"share_{name}"] = features[f"pop_{name}"] / features["pop_total"]
    features = features.reset_index().rename(columns={"code": "commune_code"})
    features["municipality_id"] = features["commune_code"].astype("string").str.zfill(4)
    month, day = AVAILABLE_MONTH_DAY
    features["available_from"] = pd.to_datetime({"year": features["year"] + 1, "month": month, "day": day})
    return features.sort_values(["commune_code", "year"], key=lambda s: s.astype(int) if s.name == "commune_code" else s)


def check(features: pd.DataFrame) -> None:
    reference = load_snapshot_codes(REFERENCE_DATE)
    assert set(features["commune_code"]) == set(reference), "commune set differs from the register"
    assert not features.isna().any().any(), "missing values"
    assert features.groupby("commune_code").size().eq(features["year"].nunique()).all(), "gaps in years"
    assert features["pop_total"].gt(0).all(), "commune with no population"
    age_sum = features[[f"pop_{g}" for g in AGE_GROUPS]].sum(axis=1)
    assert (age_sum == features["pop_total"]).all(), "age groups do not add up to the total"
    print(f"Checks passed: {features['commune_code'].nunique()} communes x {features['year'].nunique()} years")


def main() -> None:
    features = build()
    check(features)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(OUTPUT_PATH, index=False)
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} ({len(features):,} rows)")
    print(features.groupby("year")[["pop_total"]].sum().T.to_string())
    print(features[features["year"] == 2025][["share_foreign", "share_65_plus", "mean_age"]].describe().round(3).to_string())


if __name__ == "__main__":
    main()
