"""Clean the long vote table into one row per commune x vote object with yes_share.

Every row removal is a named step recorded in the returned log; nothing is corrected
silently. Rows that are kept but look inconsistent get a ``flag_*`` column instead.

Usage: python -m scripts.cleaning.clean_ofs_votes  (reads data/interim/ofs-votes/votes_all_levels.parquet,
writes data/interim/ofs-votes/votes_communes_clean.parquet and reports/cleaning_log.md)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from scripts.vote_keys import ofs_keys
from scripts.votes_config import (
    COUNT_COLUMNS,
    INTERIM_DIR,
    INTERIM_PATH,
    REPORTS_DIR,
    RESULT_COLUMNS,
    SPECIAL_UNIT_MIN_CODE,
)

CLEAN_PATH = INTERIM_DIR / "ofs-votes" / "votes_communes_clean.parquet"
CLEANING_LOG_PATH = REPORTS_DIR / "cleaning_log.md"

FRENCH_MONTHS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}

PROCESSED_COLUMNS = [
    "vote_id", "vote_key", "vote_date", "vote_title_fr", "vote_title_de", "is_tiebreak_question", "is_provisional",
    "municipality_id", "municipality_name", "municipality_name_de", "canton", "district_id", "district_name",
    "is_special_unit",
    "eligible_voters", "ballots_cast", "valid_ballots", "blank_invalid_ballots", "votes_yes", "votes_no",
    "yes_share", "turnout", "yes_pct_ofs", "turnout_pct_ofs",
    "flag_valid_gt_ballots", "flag_yes_no_gt_valid",
]


@dataclass
class CleaningLog:
    steps: list[dict] = field(default_factory=list)

    def record(self, step: str, before: int, after: int, reason: str) -> None:
        self.steps.append({"step": step, "rows_before": before, "rows_removed": before - after,
                           "rows_after": after, "reason": reason})

    def to_markdown(self) -> str:
        return pd.DataFrame(self.steps).to_markdown(index=False)


def compute_yes_share(yes: pd.Series, no: pd.Series) -> pd.Series:
    """yes / (yes + no); NaN when either is missing or when yes + no == 0."""
    total = yes + no
    return (yes / total.where(total != 0)).astype(float)


def parse_provisional_months(note_fr: str) -> set[tuple[int, int]]:
    """Extract (year, month) pairs from 'Résultats provisoires: novembre 2025, mars et juin 2026#'."""
    match = re.search(r"Résultats provisoires\s*:([^#]*)", note_fr)
    if not match:
        return set()
    months, pending = set(), []
    for word in re.findall(r"[a-zéû]+|\d{4}", match.group(1).lower()):
        if word in FRENCH_MONTHS:
            pending.append(FRENCH_MONTHS[word])
        elif word.isdigit():
            months.update((int(word), m) for m in pending)
            pending = []
    return months


def split_vote_label(labels: pd.Series) -> tuple[pd.Series, pd.Series]:
    """'2024-11-24 Titre' -> (date, 'Titre'). Unparseable dates become NaT (caught by validation)."""
    parts = labels.astype(str).str.extract(r"^(\S+)\s+(.*)$")
    return pd.to_datetime(parts[0], format="%Y-%m-%d", errors="coerce"), parts[1]


def clean_votes(frame: pd.DataFrame, provisional_months: set[tuple[int, int]] | None = None) -> tuple[pd.DataFrame, CleaningLog]:
    log = CleaningLog()
    results = list(RESULT_COLUMNS.values())

    n = len(frame)
    df = frame[frame["level"] == "commune"].copy()
    log.record("keep_commune_level", n, len(df),
               "Country/canton/district rows are aggregates of the commune rows (kept in data/interim).")

    n = len(df)
    df = df[df[results].notna().any(axis=1)]
    log.record("drop_empty_cells", n, len(df),
               "All 7 measures missing ('...'): the cube is a full commune x vote grid; no result was "
               "published for that unit and vote (pre-1981 gaps, communes without own ballot box, unused special units).")

    n = len(df)
    df = df[df["votes_yes"].notna() & df["votes_no"].notna()]
    log.record("drop_missing_yes_no", n, len(df), "Yes or No count missing: target cannot be computed.")

    n = len(df)
    df = df[(df["votes_yes"] + df["votes_no"]) != 0]
    log.record("drop_zero_yes_plus_no", n, len(df), "Yes + No = 0: yes_share undefined (division by zero).")

    out = pd.DataFrame(index=df.index)
    out["vote_id"] = df["vote_id"].astype("string")
    out["vote_key"] = ofs_keys(out["vote_id"])
    out["vote_date"], out["vote_title_de"] = split_vote_label(df["vote_label_de"])
    fr_date, out["vote_title_fr"] = split_vote_label(df["vote_label_fr"])
    if not out["vote_date"].equals(fr_date):
        raise ValueError("German and French vote labels disagree on the vote date")
    # Tie-break questions: yes = prefers the initiative, no = prefers the counter-proposal (PX NOTE).
    out["is_tiebreak_question"] = out["vote_title_de"].str.contains("Stichfrage", regex=False)
    months = provisional_months or set()
    out["is_provisional"] = [(d.year, d.month) in months if pd.notna(d) else False for d in out["vote_date"]]

    out["municipality_id"] = df["location_code"].astype("string")
    out["municipality_name"] = df["location_name_fr"].astype("string")
    out["municipality_name_de"] = df["location_name_de"].astype("string")
    out["canton"] = df["canton"].astype("string")
    out["district_id"] = df["district_code"].astype("string")
    out["district_name"] = df["district_name"].astype("string")
    out["is_special_unit"] = out["municipality_id"].astype(int) >= SPECIAL_UNIT_MIN_CODE

    for column in COUNT_COLUMNS:
        out[column] = df[column].round().astype("Int64") if (df[column].dropna() % 1 == 0).all() else df[column]
    out["blank_invalid_ballots"] = out["ballots_cast"] - out["valid_ballots"]
    out["yes_share"] = compute_yes_share(df["votes_yes"], df["votes_no"])
    out["turnout"] = (df["ballots_cast"] / df["eligible_voters"].where(df["eligible_voters"] != 0)).astype(float)
    out["yes_pct_ofs"] = df["yes_pct_ofs"]
    out["turnout_pct_ofs"] = df["turnout_pct_ofs"]

    out["flag_valid_gt_ballots"] = (df["valid_ballots"] > df["ballots_cast"]).fillna(False).astype(bool)
    out["flag_yes_no_gt_valid"] = ((df["votes_yes"] + df["votes_no"]) > df["valid_ballots"]).fillna(False).astype(bool)

    out = out[PROCESSED_COLUMNS].sort_values(["vote_date", "vote_id", "municipality_id"]).reset_index(drop=True)
    return out, log


def main() -> None:
    from scripts.cleaning.parse_ofs_votes import read_px_metadata
    from scripts.votes_config import RAW_PX_PATH

    frame = pd.read_parquet(INTERIM_PATH)
    months = parse_provisional_months("".join(read_px_metadata(RAW_PX_PATH).get("NOTE[fr]", [])))
    clean, log = clean_votes(frame, months)
    clean.to_parquet(CLEAN_PATH, index=False)
    CLEANING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLEANING_LOG_PATH.write_text("# Cleaning log\n\n" + log.to_markdown() + "\n", encoding="utf-8")
    print(log.to_markdown())
    print(f"Wrote {len(clean):,} rows to {CLEAN_PATH}")


if __name__ == "__main__":
    main()
