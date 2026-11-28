"""V26.2: quarantine audit of historical SECO/OFS unemployment-rate vintages."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

LIMIT = 5_000_000
CUTOFF = date(2023, 1, 1)
HOST = "dam-api.bfs.admin.ch"


def validate_catalog(rows):
    ids, dates = set(), set()
    for row in rows:
        ident = row["id"]
        end, pub = date.fromisoformat(row["end"]), date.fromisoformat(row["published"])
        if ident in ids or pub in dates or not end < pub < CUTOFF:
            raise ValueError("Duplicate or invalid vintage")
        if row["format"] not in {"xls", "xlsx", "csv"} or row["license"] != "OPEN-BY":
            raise ValueError("Unverified metadata")
        if row["download"] != f"https://{HOST}/hub/api/dam/assets/{ident}/master":
            raise ValueError("Unexpected download URL")
        ids.add(ident)
        dates.add(pub)


def inspect_bytes(data, fmt):
    if not 0 < len(data) <= LIMIT:
        raise ValueError("Invalid size")
    if fmt == "xls":
        if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise ValueError("Not OLE XLS")
    elif fmt == "xlsx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if "xl/workbook.xml" not in archive.namelist():
                raise ValueError("Not XLSX")
    elif fmt == "csv":
        decoded = data.decode("utf-8-sig")
        first = decoded.splitlines()[0]
        if first.lstrip().startswith("<") or not any(sep in first for sep in (",", ";", "\t")):
            raise ValueError("Not a delimited CSV")
    else:
        raise ValueError("Unknown format")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def select_vintage(rows, day, max_age_days=45):
    """Metadata-only eligibility. Never treat later releases as historical inputs."""
    if day >= CUTOFF:
        raise ValueError("Final dates forbidden")
    eligible = [
        r for r in rows
        if date.fromisoformat(r["published"]) < day
        and 0 < (day - date.fromisoformat(r["end"])).days <= max_age_days
    ]
    return max(eligible, key=lambda r: r["published"], default=None)


def read_roster(path):
    keys = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            day = date.fromisoformat(row["vote_date"])
            if not date(2016, 1, 1) <= day < CUTOFF:
                raise ValueError("Unexpected date")
            keys.add((day, row["vote_id"]))
    if len(keys) != 66 or len({k[0] for k in keys}) != 23:
        raise ValueError("Reference population changed")
    return keys


def acquire(row):
    request = Request(row["download"], headers={"User-Agent": "GML historical data audit"})
    with urlopen(request, timeout=25) as response:
        if urlsplit(response.geturl()).hostname != HOST:
            raise ValueError("Unexpected final host")
        data = response.read(LIMIT + 1)
    return inspect_bytes(data, row["format"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Preserve previous audit")
    rows = json.loads(args.catalog.read_text(encoding="utf-8"))["assets"]
    validate_catalog(rows)
    keys = read_roster(args.roster)
    results = []
    for row in rows:
        try:
            result = {**row, **acquire(row), "status": "format_checked_not_admitted"}
        except (OSError, ValueError, zipfile.BadZipFile, IndexError) as exc:
            result = {**row, "status": "blocked", "error": str(exc)}
        results.append(result)
    available = [r for r in results if r["status"] == "format_checked_not_admitted"]
    dates = sorted({k[0] for k in keys})
    matches = {str(day): select_vintage(available, day) for day in dates}
    report = {
        "status": "quarantine_only",
        "catalog_sha256": hashlib.sha256(args.catalog.read_bytes()).hexdigest(),
        "assets": results,
        "format_checked": len(available),
        "objects": len(keys),
        "dates": len(dates),
        "fresh_candidate_dates": sum(r is not None for r in matches.values()),
        "fresh_candidate_objects": sum(matches[str(day)] is not None for day, _ in keys),
        "date_asset": {day: r["id"] if r else None for day, r in matches.items()},
        "training_rows_admitted": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("SECO_VINTAGES", json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
