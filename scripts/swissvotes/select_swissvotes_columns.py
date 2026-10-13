"""Select project columns without discarding potentially useful sparse variables.

The complete cleaned source remains in interim. Rules are deliberately narrow:
unknown columns are retained, and semantic codes such as 0/9999 are not null.
Field definitions: https://swissvotes.ch/page/dataset/codebook-de.pdf
"""

import pandas as pd

CANTONS = frozenset(["zh", "be", "lu", "ur", "sz", "ow", "nw", "gl", "zg", "fr", "so", "bs", "bl", "sh", "ar", "ai", "sg", "gr", "ag", "tg", "ti", "vd", "vs", "ne", "ge", "ju"])
NATIONAL_RESULTS = frozenset({
    "volk", "stand", "annahme", "berecht", "stimmen", "bet", "leer", "ungultig",
    "gultig", "volkja", "volknein", "volkja-proz", "kt-ja", "kt-nein", "ktjaproz",
})
CANTON_RESULTS = frozenset({"berecht", "stimmen", "bet", "gultig", "ja", "nein", "japroz", "annahme"})
RESULT_FLAGS = frozenset({"flag_national_counts_inconsistent", "flag_national_pct_mismatch"})
LINK_PREFIXES = (
    "bkchrono-", "curiavista-", "info_br-", "info_dep-", "info_amt-", "easyvideo_",
    "web-yes-", "web-no-", "finanz-link-", "bkresults-", "bfsdash-", "bfsmap-", "nach_cockpit_",
)


def select_swissvotes_columns(clean: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return a column subset and a complete decision log, preserving all rows."""
    if clean.empty or not clean.columns.is_unique:
        raise ValueError("Swissvotes selection requires non-empty data with unique columns")
    decisions = []
    for column in clean.columns:
        canton, _, measure = column.partition("-")
        if clean[column].isna().all():
            reason = "entirely_empty"
        elif column in NATIONAL_RESULTS or (canton in CANTONS and measure in CANTON_RESULTS):
            reason = "voting_results_audit_only"
        elif column in RESULT_FLAGS:
            reason = "result_quality_flag_audit_only"
        elif column == "dat-force":
            reason = "post_vote_entry_into_force"
        elif column == "anr" and "swissvotes_id" in clean:
            reason = "duplicate_of_swissvotes_id"
        elif column == "datum" and "vote_date" in clean:
            reason = "raw_date_replaced_by_vote_date"
        elif column == "anneepolitique" or column.startswith(LINK_PREFIXES):
            reason = "secondary_document_link"
        else:
            reason = "retained"
        decisions.append({
            "column": column, "kept": reason == "retained", "reason": reason,
            "missing_count": int(clean[column].isna().sum()),
            "missing_share": float(clean[column].isna().mean()),
        })
    log = pd.DataFrame(decisions)
    return clean.loc[:, log.loc[log["kept"], "column"]].copy(), log
