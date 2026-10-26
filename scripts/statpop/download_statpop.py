"""Download OFS STATPOP (px-x-0102010000_101) and extract one CSV per year.

Use the complete PX export by default. The slower batched API remains available
with --method api. Both select permanent residents, nationality and single-year age.

Usage: python -m scripts.statpop.download_statpop [--force]
"""

from __future__ import annotations

import argparse
import time

import requests

from scripts.common.communes import (
    PAUSE_SECONDS,
    ROOT,
    STATPOP_RAW_DIR,
    record_provenance,
    request_with_retry,
    should_skip,
    write_atomic,
)

STATPOP_TABLE_ID = "px-x-0102010000_101"
STATPOP_API_URL = f"https://www.pxweb.bfs.admin.ch/api/v1/fr/{STATPOP_TABLE_ID}/{STATPOP_TABLE_ID}.px"
STATPOP_DOWNLOAD_URL = f"https://www.pxweb.bfs.admin.ch/DownloadFile.aspx?file={STATPOP_TABLE_ID}"
DIM_YEAR, DIM_PLACE = "Jahr", "Kanton (-) / Bezirk (>>) / Gemeinde (......)"
DIM_POPTYPE, DIM_NATIONALITY, DIM_SEX, DIM_AGE = (
    "Bevölkerungstyp", "Staatsangehörigkeit (Kategorie)", "Geschlecht", "Alter",
)
PERMANENT_POPULATION = "1"
TOTAL_CODE = "-99999"
STATPOP_BATCH_SIZE = 100  # communes per query: the firewall answers 403 to large POST bodies/results


def download_statpop(session: requests.Session, force: bool) -> None:
    """One CSV per year: communes only, permanent residents, nationality x age, both sexes."""
    metadata = request_with_retry(session, "GET", STATPOP_API_URL).json()
    variables = {variable["code"]: variable for variable in metadata["variables"]}
    years = variables[DIM_YEAR]["values"]
    place = variables[DIM_PLACE]
    communes = [code for code, text in zip(place["values"], place["valueTexts"]) if text.startswith("......")]
    print(f"STATPOP: {len(years)} years, {len(communes)} commune codes")

    for year in years:
        path = STATPOP_RAW_DIR / f"statpop_{year}.csv"
        if should_skip(path, force):
            continue
        parts = []
        for start in range(0, len(communes), STATPOP_BATCH_SIZE):
            query = {
                "query": [
                    {"code": DIM_YEAR, "selection": {"filter": "item", "values": [year]}},
                    {"code": DIM_PLACE, "selection": {"filter": "item", "values": communes[start:start + STATPOP_BATCH_SIZE]}},
                    {"code": DIM_POPTYPE, "selection": {"filter": "item", "values": [PERMANENT_POPULATION]}},
                    {"code": DIM_NATIONALITY, "selection": {"filter": "all", "values": ["*"]}},
                    {"code": DIM_SEX, "selection": {"filter": "item", "values": [TOTAL_CODE]}},
                    {"code": DIM_AGE, "selection": {"filter": "all", "values": ["*"]}},
                ],
                "response": {"format": "csv"},
            }
            response = request_with_retry(session, "POST", STATPOP_API_URL, json=query)
            lines = response.content.decode("latin-1").splitlines(keepends=True)  # PXWeb CSV is ISO-8859-1
            parts.extend(lines if not parts else lines[1:])  # keep a single header row
            time.sleep(PAUSE_SECONDS)
        write_atomic(path, "".join(parts).encode("utf-8"))
        record_provenance(
            path.stem, path, STATPOP_API_URL, table=STATPOP_TABLE_ID, year=year,
            filters="communes only, permanent residents, sex total, nationality and single-year age detail",
        )
        print(f"Saved {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")


def ensure_raw_data(force: bool = False) -> None:
    """Download the raw files that are missing (all of them with ``force``); used by run_pipeline."""
    from scripts.statpop.parse_statpop_px import extract_years

    path = STATPOP_RAW_DIR / f"{STATPOP_TABLE_ID}.px"
    if force or not path.is_file():
        response = request_with_retry(requests.Session(), "GET", STATPOP_DOWNLOAD_URL, stream=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".px.part")
        with response, partial.open("wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                handle.write(chunk)
        expected = response.headers.get("Content-Length")
        if expected and partial.stat().st_size != int(expected):
            raise RuntimeError("Incomplete STATPOP PX download")
        partial.replace(path)
        record_provenance(path.stem, path, STATPOP_DOWNLOAD_URL)
    extract_years(path, force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="replace existing raw files")
    parser.add_argument("--method", choices=("px", "api"), default="px", help="complete PX export (default) or slow API batches")
    args = parser.parse_args()
    try:
        if args.method == "api":
            download_statpop(requests.Session(), args.force)
        else:
            ensure_raw_data(args.force)
    except (requests.RequestException, RuntimeError) as error:
        raise SystemExit(f"STATPOP download failed: {error}") from error


if __name__ == "__main__":
    main()
