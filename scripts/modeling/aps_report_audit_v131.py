"""Audit contemporaneous APS report covers only, without election outcomes."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from scripts.modeling.aps_audit_v131 import day, roster

MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember")


def report_url(key):
    if not re.fullmatch(r"[0-9]+", key):
        raise ValueError("Invalid roster key")
    number = int(key)
    return f"https://swissvotes.ch/vote/{number // 10}.{number % 10}0/inserateanalyse.pdf"


def cover_status(text, vote_date):
    normalized = " ".join(text.split())
    long_date = f"{vote_date.day}. {MONTHS[vote_date.month - 1]} {vote_date.year}"
    numeric = f"{vote_date.day:02d}.{vote_date.month:02d}.{vote_date.year}"
    if "Inserateanalyse" not in normalized or not (
        long_date in normalized or numeric in normalized
    ):
        return {"status": "cover_identity_unverified"}
    match = re.search(r"Zwischenstand vom\s+(\d{1,2}\.\d{1,2}\.\d{4})", normalized)
    if not match:
        return {"status": "cover_date_unverified"}
    report_date = day(match[1])
    lead = (vote_date - report_date).days
    return {"status": "dated_candidate" if lead >= 1 else "not_prevote",
            "cover_date": report_date.isoformat(), "lead_days": lead}


def inspect(item):
    from pypdf import PdfReader

    key, vote_date = item
    url = report_url(key)
    entry = {"vote_key": key, "vote_date": vote_date.isoformat(), "url": url}
    try:
        with urlopen(url, timeout=12) as response:
            raw = response.read(15_000_001)
        if len(raw) > 15_000_000 or not raw.startswith(b"%PDF-"):
            return {**entry, "status": "not_bounded_pdf"}
        entry.update({"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        cover = PdfReader(io.BytesIO(raw)).pages[0].extract_text() or ""
        return {**entry, **cover_status(cover, vote_date)}
    except HTTPError as exc:
        return {**entry, "status": f"http_{exc.code}"}
    except (URLError, TimeoutError) as exc:
        return {**entry, "status": "network_error", "error_type": type(exc).__name__}
    except Exception as exc:  # noqa: BLE001
        return {**entry, "status": "parse_error", "error_type": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path,
                        default=Path("data/processed/municipal_v3/object_features.csv"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = roster(args.roster)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(inspect, sorted(expected.items())))
    candidates = [r for r in records if r["status"] == "dated_candidate"]
    result = {
        "objects": len(expected),
        "dates": len(set(expected.values())),
        "status_counts": dict(Counter(r["status"] for r in records)),
        "candidate_dates": len({r["vote_date"] for r in candidates}),
        "candidate_distinct_pdf_hashes": len({r["sha256"] for r in candidates}),
        "training_rows_admitted": 0,
        "strict_forecast_ready": False,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("AUDIT", json.dumps({k: v for k, v in result.items() if k != "records"}))


if __name__ == "__main__":
    main()
