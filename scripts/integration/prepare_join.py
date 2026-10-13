"""Validate an exact many-to-one OFS -> Swissvotes join and publish its crosswalk.

Usage: python -m scripts.integration.prepare_join
No date-only, title-based, fuzzy or rounded identifier matching is allowed.
"""

from __future__ import annotations

import pandas as pd

from scripts.common.config import (
    JOIN_REPORT_PATH,
    PROCESSED_PATH,
    SWISSVOTES_CLEAN_PATH,
    VOTE_CROSSWALK_PATH,
)
from scripts.common.vote_keys import ofs_keys, swissvotes_key


def prepare_join(ofs: pd.DataFrame, swiss: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Return all OFS vote objects, unmatched Swissvotes objects, and a quality report.

    A row in the crosswalk is one vote question. A row in OFS remains one
    municipality x question; an unmatched or ambiguous OFS key blocks publication.
    """
    left_columns = ["vote_key", "vote_id", "vote_date", "is_tiebreak_question"]
    right_columns = ["vote_key", "swissvotes_id", "vote_date", "is_tiebreak_question"]
    for frame, columns, name in ((ofs, left_columns + ["municipality_id"], "OFS"),
                                 (swiss, right_columns, "Swissvotes")):
        if frame.empty or not set(columns).issubset(frame.columns):
            raise ValueError(f"{name}: empty data or missing join fields")
        if frame[columns].isna().any().any():
            raise ValueError(f"{name}: null join identifiers, dates or question types")
        if not pd.api.types.is_datetime64_any_dtype(frame["vote_date"]):
            raise ValueError(f"{name}: vote_date must be a parsed date")
        if not frame["vote_key"].astype("string").str.fullmatch(r"[1-9][0-9]*").all():
            raise ValueError(f"{name}: malformed vote_key")
    if swiss["vote_key"].duplicated().any():
        raise ValueError("Swissvotes: vote_key must be unique for a many-to-one join")
    if not ofs_keys(ofs["vote_id"]).eq(ofs["vote_key"]).all():
        raise ValueError("OFS: vote_key does not match the original identifier")
    if not swiss["swissvotes_id"].map(swissvotes_key).eq(swiss["vote_key"]).all():
        raise ValueError("Swissvotes: vote_key does not match the original identifier")
    if ofs.duplicated(["vote_key", "municipality_id"]).any():
        raise ValueError("OFS: duplicate municipality x vote_key")
    questions = ofs[left_columns].drop_duplicates()
    if questions["vote_key"].duplicated().any():
        raise ValueError("OFS: a vote_key has conflicting identifiers, dates or question types")
    crosswalk = questions.merge(swiss[right_columns], on="vote_key", how="outer",
                               suffixes=("", "_swissvotes"), validate="one_to_one", indicator=True)
    extras = crosswalk.loc[crosswalk["_merge"] == "right_only", right_columns[:2] +
                           ["vote_date_swissvotes", "is_tiebreak_question_swissvotes"]].copy()
    minimum, maximum = ofs["vote_date"].min(), ofs["vote_date"].max()
    extras["reason"] = "not_in_clean_ofs"
    extras.loc[extras["vote_date_swissvotes"] < minimum, "reason"] = "before_ofs_coverage"
    extras.loc[extras["vote_date_swissvotes"] > maximum, "reason"] = "after_ofs_coverage"
    crosswalk = crosswalk.loc[crosswalk["_merge"] != "right_only"].copy()
    crosswalk["join_status"] = "matched"
    crosswalk.loc[crosswalk["_merge"] == "left_only", "join_status"] = "missing_swissvotes"
    matched = crosswalk["_merge"] == "both"
    crosswalk.loc[matched & crosswalk["vote_date"].ne(crosswalk["vote_date_swissvotes"]),
                  "join_status"] = "date_mismatch"
    crosswalk.loc[matched & crosswalk["is_tiebreak_question"].ne(crosswalk["is_tiebreak_question_swissvotes"]),
                  "join_status"] = "question_type_mismatch"
    crosswalk = crosswalk.drop(columns="_merge").sort_values(["vote_date", "vote_key"]).reset_index(drop=True)
    failures = crosswalk.loc[crosswalk["join_status"] != "matched"]
    # Uniqueness checks above establish many-to-one cardinality without a municipal join.
    report = (
        "# OFS / Swissvotes join preparation\n\n"
        f"Status: {'PASS' if failures.empty else 'FAIL'}\n\n"
        f"OFS municipal rows: {len(ofs):,}; no municipal join performed.\n\n"
        f"OFS vote objects: {len(questions)}; Swissvotes vote objects: {len(swiss)}.\n\n"
        f"Matched, date- and question-type-checked OFS objects: {len(crosswalk) - len(failures)}.\n\n"
        f"Unmatched/conflicting OFS objects: {len(failures)}.\n\n"
        f"Swissvotes objects outside the cleaned OFS keys: {len(extras)}.\n\n"
        "The key is the OFS question code, or the exact Swissvotes `anr * 10`. "
        "Initiatives, counter-proposals and tie-break questions remain separate. "
        "Dates and question types are independent consistency checks, not matching keys.\n\n"
        "The final join must use `on='vote_key', how='left', validate='many_to_one'`. "
        "The crosswalk has one row per OFS vote object; it does not aggregate communes. "
        "No Swissvotes feature columns have yet been replicated into the municipal table.\n\n"
        "Swissvotes includes national results, campaign outcomes and other post-vote fields: "
        "select model features according to the prediction date to avoid target leakage.\n\n"
        "## OFS discrepancies\n\n" + (failures.to_markdown(index=False) if not failures.empty else "None.") +
        "\n\n## Swissvotes outside OFS coverage\n\n" +
        (extras.groupby("reason").size().rename("votes").to_markdown() if not extras.empty else "None.") + "\n"
    )
    return crosswalk, extras, report


def main() -> None:
    JOIN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        crosswalk, extras, report = prepare_join(
            pd.read_parquet(PROCESSED_PATH), pd.read_parquet(SWISSVOTES_CLEAN_PATH)
        )
    except ValueError as error:
        JOIN_REPORT_PATH.write_text(f"# Join preparation FAILED\n\n{error}\n", encoding="utf-8")
        raise
    JOIN_REPORT_PATH.write_text(report, encoding="utf-8")
    crosswalk.to_csv(JOIN_REPORT_PATH.with_name("join_crosswalk.csv"), index=False)
    extras.to_csv(JOIN_REPORT_PATH.with_name("swissvotes_without_ofs.csv"), index=False)
    if crosswalk["join_status"].ne("matched").any():
        raise ValueError(f"Join preparation failed; inspect {JOIN_REPORT_PATH}")
    VOTE_CROSSWALK_PATH.parent.mkdir(parents=True, exist_ok=True)
    crosswalk.to_parquet(VOTE_CROSSWALK_PATH, index=False)
    print(f"Join ready: {len(crosswalk)} vote objects -> {VOTE_CROSSWALK_PATH}")


if __name__ == "__main__":
    main()
