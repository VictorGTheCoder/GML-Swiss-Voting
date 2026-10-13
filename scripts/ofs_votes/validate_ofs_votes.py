"""Automatic checks on the cleaned commune x vote table.

"error" checks encode fundamental assumptions (unique unit of observation, target in
[0, 1], ...): any failure raises ValidationError and nothing is written to
data/processed. "warning" checks count known, documented inconsistencies that are
kept and flagged rather than dropped.

Usage: python -m scripts.ofs_votes.validate_ofs_votes  (reads data/interim/ofs-votes/votes_communes_clean.parquet,
writes reports/validation_report.md and, if all error checks pass, data/processed/)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd

from scripts.common.config import COUNT_COLUMNS, PROCESSED_PATH, REPORTS_DIR

VALIDATION_REPORT_PATH = REPORTS_DIR / "validation_report.md"
REQUIRED_NON_NULL = ["vote_id", "vote_key", "vote_date", "municipality_id", "municipality_name", "canton",
                     "votes_yes", "votes_no", "yes_share"]
FIRST_POSSIBLE_DATE = pd.Timestamp("1960-01-01")
# OFS percentages carry 7 decimals, i.e. an absolute error below 1e-7 on a 0-100 scale.
PCT_TOLERANCE = 1e-6


class ValidationError(Exception):
    pass


@dataclass
class CheckResult:
    name: str
    severity: str  # "error" | "warning"
    n_failed: int
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.n_failed == 0


def _check(name: str, failed: pd.Series | int, detail: str = "", severity: str = "error") -> CheckResult:
    n_failed = int(failed.sum()) if isinstance(failed, pd.Series) else int(failed)
    return CheckResult(name, severity, n_failed, detail)


def run_checks(df: pd.DataFrame, today: date | None = None) -> list[CheckResult]:
    last_possible = pd.Timestamp(today or pd.Timestamp.now(tz=ZoneInfo("Europe/Zurich")).date())
    yes_no = df["votes_yes"] + df["votes_no"]
    checks = [_check("non_empty", int(df.empty))]
    checks += [_check(f"not_null:{c}", df[c].isna()) for c in REQUIRED_NON_NULL]
    checks += [
        _check("unique:vote_id x municipality_id", df.duplicated(["vote_id", "municipality_id"], keep=False),
               "the unit of observation must be unique"),
        _check("vote_key equals OFS vote_id", df["vote_key"].ne(df["vote_id"])),
        _check("vote_key is a positive integer identifier",
               ~df["vote_key"].astype("string").str.fullmatch(r"[1-9][0-9]*", na=False)),
        _check("vote_date in [1960-01-01, today]",
               ~df["vote_date"].between(FIRST_POSSIBLE_DATE, last_possible) & df["vote_date"].notna()),
        _check("one date per vote_id", df.groupby("vote_id", observed=True)["vote_date"].nunique().gt(1)),
        _check("one name per municipality_id",
               df.groupby("municipality_id", observed=True)["municipality_name"].nunique().gt(1)),
        _check("one canton per municipality_id", df.groupby("municipality_id", observed=True)["canton"].nunique().gt(1)),
    ]
    checks += [_check(f"non_negative:{c}", df[c] < 0) for c in COUNT_COLUMNS]
    checks += [_check(f"integer:{c}", df[c].notna() & df[c].mod(1).ne(0)) for c in COUNT_COLUMNS]
    checks += [
        _check("yes_share agrees with counts", (df["yes_share"] - df["votes_yes"] / yes_no).abs().gt(1e-12)),
        _check("positive yes + no", yes_no.le(0)),
    ]
    checks += [
        _check("yes_share in [0, 1]", ~df["yes_share"].between(0, 1) & df["yes_share"].notna()),
        _check("yes_share == OFS 'Oui en %' / 100",
               (df["yes_share"] * 100 - df["yes_pct_ofs"]).abs().gt(PCT_TOLERANCE),
               "recomputed target agrees with the published percentage"),
        _check("turnout == OFS 'Participation en %' / 100",
               (df["turnout"] * 100 - df["turnout_pct_ofs"]).abs().gt(PCT_TOLERANCE)),
        _check("ballots_cast <= eligible_voters", df["ballots_cast"] > df["eligible_voters"]),
        _check("valid_ballots <= ballots_cast", df["flag_valid_gt_ballots"],
               "kept, flagged in flag_valid_gt_ballots", severity="warning"),
        _check("votes_yes + votes_no <= valid_ballots", df["flag_yes_no_gt_valid"],
               "kept, flagged in flag_yes_no_gt_valid", severity="warning"),
        _check("eligible_voters or ballots_cast available",
               df["eligible_voters"].isna() | df["ballots_cast"].isna(),
               "turnout cannot be computed for these rows (yes_share still valid)", severity="warning"),
    ]
    # Informative only: yes + no < valid is structural when one ballot carries several questions
    # (initiative + counter-proposal + tie-break), since a question may be left blank.
    checks.append(_check("votes_yes + votes_no == valid_ballots", yes_no < df["valid_ballots"],
                         "yes+no < valid: expected on multi-question ballots, not an error", severity="warning"))
    return checks


def checks_to_markdown(checks: list[CheckResult], n_rows: int) -> str:
    table = pd.DataFrame([{"check": c.name, "severity": c.severity, "status": "PASS" if c.passed else "FAIL",
                           "n_failed": c.n_failed, "detail": c.detail} for c in checks])
    return (f"# Validation report\n\nRows checked: {n_rows:,}\n\n{table.to_markdown(index=False)}\n\n"
            "`error` failures abort the pipeline; `warning` rows are kept and flagged.\n")


def assert_valid(checks: list[CheckResult]) -> None:
    failed = [c for c in checks if c.severity == "error" and not c.passed]
    if failed:
        raise ValidationError("; ".join(f"{c.name} ({c.n_failed} rows)" for c in failed))


def main() -> None:
    from scripts.ofs_votes.clean_ofs_votes import CLEAN_PATH

    df = pd.read_parquet(CLEAN_PATH)
    checks = run_checks(df)
    VALIDATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_REPORT_PATH.write_text(checks_to_markdown(checks, len(df)), encoding="utf-8")
    assert_valid(checks)
    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_PATH, index=False)
    print(f"All error checks passed; wrote {PROCESSED_PATH}")


if __name__ == "__main__":
    main()
