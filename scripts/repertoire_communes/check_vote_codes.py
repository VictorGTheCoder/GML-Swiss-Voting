"""Check that commune codes of the vote results match the commune register at each vote date.

For every vote date of the interim table (data/interim/ofs-votes/votes_all_levels.parquet, built by
scripts.ofs_votes.parse_ofs_votes) the register snapshot at that date is downloaded (cached in
data/raw/repertoire_communes/vote_snapshots/) and compared with the communes that have results.
Every code is followed to the reference date with commune_crosswalk.resolve(). The cube
does not use the codes of the vote date: early votes carry later codes (e.g. Zürich is 261
in 1960, a code assigned in 1990), so a code missing from the register is only a problem
when its descendants are not among those of the register's communes ("lineage mismatch").

Usage: python -m scripts.repertoire_communes.check_vote_codes [--to 2026-01-01]
Writes reports/datasets/repertoire_communes/vote_code_check.csv (one row per vote date) and prints a summary.
"""

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from scripts.common.communes import (
    AGVCH_BASE,
    REGISTER_RAW_DIR,
    REGISTER_REPORTS_DIR,
    ROOT,
    fr_date,
    request_with_retry,
    write_atomic,
)
from scripts.common.config import INTERIM_PATH
from scripts.repertoire_communes.commune_crosswalk import (
    load_mutations,
    load_snapshot_codes,
    resolve,
)

SNAPSHOT_DIR = REGISTER_RAW_DIR / "vote_snapshots"
REPORT_PATH = REGISTER_REPORTS_DIR / "vote_code_check.csv"
SPECIAL_UNIT_MIN_CODE = 9000  # Swiss abroad, correspondence votes, unassigned ballots
PAUSE_SECONDS = 0.5


def fetch_snapshot(session: requests.Session, day: date) -> Path:
    path = SNAPSHOT_DIR / f"snapshot_{day.isoformat()}.csv"
    if not path.exists():
        response = request_with_retry(
            session, "GET", f"{AGVCH_BASE}/api/communes/snapshot", params={"date": fr_date(day), "useBfsCode": "true"},
        )
        write_atomic(path, response.content)
        time.sleep(PAUSE_SECONDS)
    return path


def snapshot_codes(path: Path) -> set[str]:
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    return set(frame.loc[frame["Level"] == "3", "BfsCode"])


def commune_results() -> pd.DataFrame:
    votes = pd.read_parquet(INTERIM_PATH)
    communes = votes[votes["level"] == "commune"].copy()
    communes["vote_date"] = pd.to_datetime(communes["vote_label_fr"].str[:10], format="%Y-%m-%d")
    communes["code"] = communes["location_code"].str.lstrip("0")
    has_result = communes[["eligible_voters", "votes_yes", "votes_no"]].notna().any(axis=1)
    return communes[has_result]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--to", dest="to_date", type=date.fromisoformat, default=date(2026, 1, 1))
    args = parser.parse_args()

    results = commune_results()
    special = results["code"].astype(int) >= SPECIAL_UNIT_MIN_CODE
    print(f"{len(results):,} commune result rows, {special.sum():,} special units (code >= 9000) set aside")
    results = results[~special]

    target = load_snapshot_codes(args.to_date)
    mutations = load_mutations()
    session = requests.Session()
    rows = []
    dates = sorted(results["vote_date"].dt.date.unique())
    for index, day in enumerate(dates, 1):
        in_votes = set(results.loc[results["vote_date"].dt.date == day, "code"])
        in_register = snapshot_codes(fetch_snapshot(session, day))
        register_targets = set()
        for code in in_register:
            register_targets |= resolve(code, day, args.to_date, mutations)
        followed = set()
        unresolved = set()
        lineage_mismatch = set()
        for code in in_votes:
            targets = resolve(code, day, args.to_date, mutations)
            followed |= targets
            if not targets <= set(target):
                unresolved.add(code)
            if code not in in_register and not targets <= register_targets:
                lineage_mismatch.add(code)
        rows.append({
            "vote_date": day.isoformat(), "communes_in_votes": len(in_votes), "communes_in_register": len(in_register),
            "only_in_votes": len(in_votes - in_register), "only_in_register": len(in_register - in_votes),
            "only_in_votes_codes": " ".join(sorted(in_votes - in_register, key=int)[:10]),
            "only_in_register_codes": " ".join(sorted(in_register - in_votes, key=int)[:10]),
            "lineage_mismatch": len(lineage_mismatch), "lineage_mismatch_codes": " ".join(sorted(lineage_mismatch, key=int)[:10]),
            "codes_not_resolving_to_target": len(unresolved), "target_communes_reached": len(followed & set(target)),
        })
        if index % 25 == 0:
            print(f"  {index}/{len(dates)} dates")

    report = pd.DataFrame(rows)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_PATH, index=False)
    print(f"\n{len(report)} vote dates; communes with results per date: "
          f"{report['communes_in_votes'].min()} to {report['communes_in_votes'].max()} "
          f"(target snapshot: {len(target)})")
    print(f"codes absent from the register at the vote date (later codes used by the cube): "
          f"{report['only_in_votes'].min()} to {report['only_in_votes'].max()} per date")
    print(f"dates with lineage mismatch: {(report['lineage_mismatch'] > 0).sum()} "
          f"(total {report['lineage_mismatch'].sum()} code-dates)")
    print(f"codes not resolving to a commune of {args.to_date}: {report['codes_not_resolving_to_target'].sum()} code-dates")
    print(f"Report written to {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
