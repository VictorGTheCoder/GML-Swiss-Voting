"""V13.1: target-blind audit of public national referendum press archive."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.request import urlopen

URL = "https://anneepolitique.swiss/wp-content/uploads/2026/05/Datensatz-der-Abstimmungsinserate_20260308.csv"
BOOK = "https://anneepolitique.swiss/wp-content/uploads/2026/06/Codebook-zum-Datensatz-der-Abstimmungsinserate_20260308.pdf"
COLUMNS = {"id.of.ad", "publication.date", "voting.date", "link.to.swissvotes"}


def day(value):
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()  # noqa: DTZ007 — calendar date only
        except ValueError:
            continue
    raise ValueError("Unrecognized date format")


def key_from_link(value):
    match = re.fullmatch(r"https?://(?:www\.)?swissvotes\.ch/vote/(\d+)(?:\.(\d{1,2}))?/?", value.strip())
    if not match:
        return None
    fraction = (match[2] or "0").ljust(2, "0")
    if int(fraction) % 10:
        return None
    return str(int(match[1]) * 10 + int(fraction) // 10)


def roster(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = csv.DictReader(source)
        result = {}
        for row in rows:
            dt = day(row["vote_date"])
            if date(2016, 1, 1) <= dt <= date(2022, 12, 31):
                key = row["vote_key"]
                if key in result:
                    raise ValueError("Duplicate roster key")
                result[key] = dt
    if len(result) != 66 or len(set(result.values())) != 23:
        raise ValueError("Reference roster mismatch")
    return result


def audit(raw, expected):
    # Only read the documented identifiers and publication dates. No outcomes,
    # ad positions, newspaper-level profiles or content are exported.
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = raw.decode("cp1252")
    dialect = csv.Sniffer().sniff(decoded[:16000], delimiters=",;\t")
    rows = csv.DictReader(io.StringIO(decoded), dialect=dialect)
    if not COLUMNS.issubset(rows.fieldnames or []):
        raise ValueError("Unexpected source schema")
    counters = Counter()
    seen = defaultdict(set)
    for row in rows:
        dt = day(row["voting.date"])
        if not date(2016, 1, 1) <= dt <= date(2022, 12, 31):
            continue
        key = key_from_link(row["link.to.swissvotes"])
        if key not in expected or expected[key] != dt:
            counters["unmatched_development_rows"] += 1
            continue
        lead = (dt - day(row["publication.date"])).days
        if not 11 <= lead <= 56:
            counters["outside_j11_window"] += 1
            continue
        ident = row["id.of.ad"].strip()
        if not ident:
            counters["missing_ad_id"] += 1
            continue
        if ident in seen[key]:
            counters["duplicate_id_within_object"] += 1
        seen[key].add(ident)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "expected_objects": len(expected),
        "objects_with_observed_prevote_records": len(seen),
        "dates_with_observed_prevote_records": len({expected[k] for k in seen}),
        "missing_object_keys": sorted(set(expected) - set(seen)),
        "matched_unique_records": sum(map(len, seen.values())),
        "diagnostics": dict(counters),
        "strict_forecast_ready": False,
        "training_rows_admitted": 0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--roster", type=Path, default=Path("data/processed/municipal_v3/object_features.csv"))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    expected = roster(args.roster)
    with urlopen(URL, timeout=45) as response:
        raw = response.read(50_000_001)
    if len(raw) > 50_000_000:
        raise ValueError("Source too large")
    result = audit(raw, expected)
    result.update({"source": URL, "codebook": BOOK, "doi": "10.48620/98224",
                   "vintage": "2026-03-08", "license": "CC BY (dataset), CC0 (codebook)",
                   "window_days_before_vote": [11, 56],
                   "availability": "retrospective edition; contemporaneous report match required"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("AUDIT", json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
