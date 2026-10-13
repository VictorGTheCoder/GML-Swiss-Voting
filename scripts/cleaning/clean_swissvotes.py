"""Clean Swissvotes without conflating missing values and documented category codes.

Usage: python -m scripts.cleaning.clean_swissvotes
Codebook: https://swissvotes.ch/page/dataset/codebook-de.pdf
All source columns are retained; only explicitly identified measures are numeric.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from scripts.vote_keys import swissvotes_key
from scripts.votes_config import (
    SWISSVOTES_CLEAN_PATH,
    SWISSVOTES_PATH,
    SWISSVOTES_REPORT_PATH,
)

REQUIRED = {"anr", "datum", "titel_kurz_d", "titel_kurz_f", "rechtsform"}
CANTONS = ["zh", "be", "lu", "ur", "sz", "ow", "nw", "gl", "zg", "fr", "so", "bs", "bl", "sh", "ar", "ai", "sg", "gr", "ag", "tg", "ti", "vd", "vs", "ne", "ge", "ju"]
COUNT_FIELDS = {"berecht", "stimmen", "leer", "ungultig", "gultig", "volkja", "volknein", "anzahl"}
COUNT_FIELDS |= {f"{c}-{measure}" for c in CANTONS for measure in ("berecht", "stimmen", "gultig", "ja", "nein")}
PERCENT_FIELDS = {"bet", "volkja-proz", "ktjaproz"}
PERCENT_FIELDS |= {f"{c}-{measure}" for c in CANTONS for measure in ("bet", "japroz")}


def _numeric(values: pd.Series, name: str, integer: bool = False) -> pd.Series:
    converted = pd.to_numeric(values, errors="coerce")
    bad = values.notna() & (converted.isna() | ~np.isfinite(converted))
    if bad.any():
        raise ValueError(f"Swissvotes {name}: invalid numeric values {values[bad].head().tolist()}")
    if integer and converted.dropna().mod(1).ne(0).any():
        raise ValueError(f"Swissvotes {name}: fractional count")
    return converted.astype("Int64" if integer else "Float64")


def clean_swissvotes(raw: pd.DataFrame, today: date | None = None) -> tuple[pd.DataFrame, str]:
    if raw.empty or not REQUIRED.issubset(raw.columns) or not raw.columns.is_unique:
        raise ValueError(f"Swissvotes must be non-empty with unique columns including {sorted(REQUIRED)}")
    # Preserve NA-like words and all category codes, notably 0 and 9999.
    df = raw.astype("string").apply(lambda col: col.str.normalize("NFC").str.strip())
    missing_before = int(df.isna().sum().sum())
    df = df.replace({"": pd.NA, ".": pd.NA})
    missing_added = int(df.isna().sum().sum()) - missing_before
    if df[list(REQUIRED)].isna().any().any():
        raise ValueError("Swissvotes: missing identifier, voting date, title or legal form")
    df["swissvotes_id"] = df["anr"]
    df["vote_key"] = df["anr"].map(swissvotes_key).astype("string")
    if df["vote_key"].duplicated().any():
        duplicates = df.loc[df["vote_key"].duplicated(keep=False), "anr"].tolist()
        raise ValueError(f"Swissvotes: duplicate normalized identifiers {duplicates}")
    df["vote_date"] = pd.to_datetime(df["datum"], format="%d.%m.%Y", errors="coerce")
    if df["vote_date"].isna().any() or df["vote_date"].lt(pd.Timestamp("1848-01-01")).any():
        raise ValueError("Swissvotes: invalid voting dates")
    df["rechtsform"] = _numeric(df["rechtsform"], "rechtsform", integer=True)
    if not df["rechtsform"].isin([1, 2, 3, 4, 5]).all():
        raise ValueError("Swissvotes: unknown legal form")
    for name in sorted(COUNT_FIELDS & set(df.columns)):
        df[name] = _numeric(df[name], name, integer=True)
        if df[name].lt(0).any():
            raise ValueError(f"Swissvotes {name}: negative count")
    for name in sorted(PERCENT_FIELDS & set(df.columns)):
        df[name] = _numeric(df[name], name)
        if (df[name].notna() & ~df[name].between(0, 100)).any():
            raise ValueError(f"Swissvotes {name}: percentage outside [0, 100]")
    df["is_tiebreak_question"] = df["rechtsform"].eq(5).astype(bool)
    cutoff = pd.Timestamp(today or pd.Timestamp.now(tz="Europe/Zurich").date())
    df["is_future_vote"] = df["vote_date"].gt(cutoff)
    # Historical inconsistencies are exposed, not repaired or silently removed.
    bad_counts = pd.Series(False, index=df.index)
    for smaller, larger in (("stimmen", "berecht"), ("gultig", "stimmen")):
        if {smaller, larger}.issubset(df.columns):
            bad_counts |= df[smaller].gt(df[larger]).fillna(False)
    bad_pct = pd.Series(False, index=df.index)
    if {"volkja", "volknein"}.issubset(df.columns):
        total = df["volkja"] + df["volknein"]
        if "gultig" in df:
            bad_counts |= total.gt(df["gultig"]).fillna(False)
        if "volkja-proz" in df:
            recomputed = 100 * df["volkja"] / total.where(total.ne(0))
            bad_pct = recomputed.sub(df["volkja-proz"]).abs().gt(0.011).fillna(False)
    df["flag_national_counts_inconsistent"] = bad_counts.astype(bool)
    df["flag_national_pct_mismatch"] = bad_pct.astype(bool)
    df = df.sort_values(["vote_date", "vote_key"]).reset_index(drop=True)
    profile = pd.DataFrame({"dtype": df.dtypes.astype(str), "missing": df.isna().sum()})
    report = (
        "# Swissvotes cleaning and validation\n\n"
        f"Rows: {len(raw):,} -> {len(df):,}; no rows removed or imputed.\n\n"
        f"Columns: {len(raw.columns)} source columns retained; {len(df.columns)} total.\n\n"
        f"Blank / dot cells converted to null: {missing_added:,}.\n\n"
        f"Future votes retained and flagged (as of {cutoff.date()}): {df['is_future_vote'].sum()}.\n\n"
        f"National count inconsistencies flagged: {bad_counts.sum()}; "
        f"national percentage discrepancies flagged: {bad_pct.sum()}.\n\n"
        "Required fields, normalized key uniqueness, dates, legal forms, nonnegative integer "
        "counts and percentage ranges: PASS.\n\n"
        "Text is trimmed and Unicode-normalized. Empty cells and `.` become null. "
        "Codes `0` and `9999` retain their field-specific meaning; they are not global missing values. "
        "Other source fields remain strings, including category codes and procedural dates with "
        "special values. These need field-specific encoding before modelling.\n\n"
        "Percentage flags compare the published share with `yes / (yes + no)`. A discrepancy "
        "is not automatically a source error: ballot conventions and denominators can differ. "
        "Published values are retained, never overwritten by the recomputed share.\n\n"
        "`vote_key = Decimal(anr) * 10`, stored as a string without floating-point rounding. "
        "Dates and question types are checked against OFS during join preparation.\n\n"
        "Source: [Swissvotes codebook](https://swissvotes.ch/page/dataset/codebook-de.pdf).\n\n"
        + profile.to_markdown() + "\n"
    )
    return df, report


def main() -> None:
    raw = pd.read_csv(SWISSVOTES_PATH, sep=";", encoding="utf-8-sig", dtype="string", keep_default_na=False)
    SWISSVOTES_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        clean, report = clean_swissvotes(raw)
    except ValueError as error:
        SWISSVOTES_REPORT_PATH.write_text(f"# Swissvotes validation FAILED\n\n{error}\n", encoding="utf-8")
        raise
    SWISSVOTES_REPORT_PATH.write_text(report, encoding="utf-8")
    flagged = clean[clean["flag_national_counts_inconsistent"] | clean["flag_national_pct_mismatch"]]
    issue_columns = ["swissvotes_id", "vote_key", "vote_date", "titel_kurz_f", "rechtsform",
                     "berecht", "stimmen", "gultig", "volkja", "volknein", "volkja-proz",
                     "flag_national_counts_inconsistent", "flag_national_pct_mismatch"]
    flagged[[c for c in issue_columns if c in flagged]].to_csv(
        SWISSVOTES_REPORT_PATH.with_name("swissvotes_quality_issues.csv"), index=False
    )
    SWISSVOTES_CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(SWISSVOTES_CLEAN_PATH, index=False)
    print(f"Swissvotes: {len(clean):,} validated votes -> {SWISSVOTES_CLEAN_PATH}")


if __name__ == "__main__":
    main()
