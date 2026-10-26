"""Download the OFS Répertoire historique des communes (agvchapp API) into data/raw/repertoire_communes/.

Snapshots of the communes at reference dates and the full mutation history since 1960, used to
harmonise commune codes between datasets.

Usage: python -m scripts.repertoire_communes.download_repertoire [--force]
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from scripts.common.communes import (
    AGVCH_BASE,
    REFERENCE_DATE,
    REGISTER_RAW_DIR,
    ROOT,
    fr_date,
    record_provenance,
    request_with_retry,
    should_skip,
    write_atomic,
)

SNAPSHOT_DATES = [date(2010, 1, 1), REFERENCE_DATE]
MUTATIONS_START = date(1960, 1, 1)


def download_repertoire(session: requests.Session, force: bool) -> None:
    """Snapshots at the given dates + full mutation history (end date cannot be in the future)."""
    for day in SNAPSHOT_DATES:
        path = REGISTER_RAW_DIR / f"snapshot_{day.isoformat()}.csv"
        if should_skip(path, force):
            continue
        url = f"{AGVCH_BASE}/api/communes/snapshot"
        response = request_with_retry(session, "GET", url, params={"date": fr_date(day), "useBfsCode": "true"})
        content = response.content
        if not content.lstrip(b"\xef\xbb\xbf").startswith(b"HistoricalCode"):
            raise RuntimeError(f"Unexpected snapshot payload: {content[:80]!r}")
        write_atomic(path, content)
        record_provenance(path.stem, path, response.url, snapshot_date=day.isoformat())
        print(f"Saved {path.relative_to(ROOT)} ({len(content):,} bytes)")

    path = REGISTER_RAW_DIR / "mutations.csv"
    if should_skip(path, force):
        return
    end = datetime.now(ZoneInfo("Europe/Zurich")).date()
    params = {"includeTerritoryExchange": "false", "startPeriod": fr_date(MUTATIONS_START), "endPeriod": fr_date(end)}
    response = request_with_retry(session, "GET", f"{AGVCH_BASE}/api/communes/mutations", params=params)
    if not response.content.lstrip(b"\xef\xbb\xbf").startswith(b"MutationNumber"):
        raise RuntimeError(f"Unexpected mutations payload: {response.content[:80]!r}")
    write_atomic(path, response.content)
    record_provenance("mutations", path, response.url, start=MUTATIONS_START.isoformat(), end=end.isoformat())
    print(f"Saved {path.relative_to(ROOT)} ({len(response.content):,} bytes)")


def ensure_raw_data(force: bool = False) -> None:
    """Download the raw files that are missing (all of them with ``force``); used by run_pipeline."""
    download_repertoire(requests.Session(), force)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="replace existing raw files")
    args = parser.parse_args()
    try:
        ensure_raw_data(args.force)
    except (requests.RequestException, RuntimeError) as error:
        raise SystemExit(f"Répertoire download failed: {error}") from error


if __name__ == "__main__":
    main()
