"""Discover and cache French Federal Chancellery brochures for local replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import pandas as pd

ARCHIVE_URL = "https://www.bk.admin.ch/fr/compilation-des-explications-du-conseil-federal-depuis-1978"
_DATE = re.compile(r"(?:19|20)\d{2}-\d{2}-\d{2}")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag == "a":
            self.href = None

    def handle_data(self, data):
        if self.href:
            self.items.append((self.href, data))


def parse_archive_entries(html: str, *, start_year: int = 2011, end_year: int = 2026) -> list[dict]:
    parser = _Links()
    parser.feed(html)
    result = {}
    for href, label in parser.items:
        absolute = urljoin(ARCHIVE_URL, href)
        if urlparse(absolute).hostname not in {"www.bk.admin.ch", "bk.admin.ch"} or not absolute.lower().split("?")[0].endswith(".pdf"):
            continue
        match = _DATE.search(label) or _DATE.search(absolute)
        if not match:
            continue
        date = match.group(0)
        if start_year <= int(date[:4]) <= end_year:
            entry = {"vote_date": date, "official_url": absolute}
            if date in result and result[date] != entry:
                raise ValueError(f"multiple official PDF links found for vote date {date}")
            result[date] = entry
    return [result[key] for key in sorted(result)]


def collect(manifest_path: Path, cache_dir: Path, ofs_path: Path, *, archive_url: str = ARCHIVE_URL,
            start_year: int = 2011, end_year: int = 2026) -> dict:
    request = Request(archive_url, headers={"User-Agent": "GML-Swiss-Voting-research/1.0"})
    with urlopen(request, timeout=60) as response:
        html = response.read().decode("utf-8", errors="replace")
    entries = parse_archive_entries(html, start_year=start_year, end_year=end_year)
    if not entries:
        raise ValueError("No official brochures discovered for the requested period")
    ofs = pd.read_parquet(ofs_path) if ofs_path.suffix == ".parquet" else pd.read_csv(ofs_path, dtype={"vote_id": "string"})
    ofs["vote_id"] = ofs.vote_id.astype(str)
    ofs["vote_date"] = pd.to_datetime(ofs.vote_date).dt.strftime("%Y-%m-%d")
    cache_dir.mkdir(parents=True, exist_ok=True)
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    docs = []
    for entry in entries:
        date = entry["vote_date"]
        req = Request(entry["official_url"], headers={"User-Agent": "GML-Swiss-Voting-research/1.0"})
        with urlopen(req, timeout=90) as response:
            raw = response.read()
        if not raw.startswith(b"%PDF-"):
            raise ValueError(f"Archive link did not return a PDF: {entry['official_url']}")
        digest = hashlib.sha256(raw).hexdigest()
        target = cache_dir / f"{digest}.pdf"
        if not target.exists():
            target.write_bytes(raw)
        vote_ids = sorted(ofs.loc[ofs.vote_date == date, "vote_id"].unique().tolist())
        docs.append({
            "source_id": f"bk-fr-{date}-{digest[:12]}", "pdf_path": str(target.resolve()),
            "official_url": entry["official_url"], "vote_date": date, "language": "fr",
            "collected_at": collected_at, "availability_status": "INVESTIGATE",
            "availability_evidence": "Archive collection timestamp does not establish pre-vote availability.",
            "ofs_vote_ids": vote_ids, "match_status": "UNRESOLVED",
            "match_justification": "Vote-date grouping only; object-section correspondence requires review.",
            "semantic_status": "NOT_VALIDATED", "pdf_sha256": digest,
        })
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "archive_url": archive_url, "collected_at": collected_at,
        "period": f"{start_year}-01-01/{end_year}-12-31", "documents": docs,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"documents": len(docs), "manifest": str(manifest_path), "cache": str(cache_dir)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ofs", type=Path, required=True, help="Read-only OFS CSV/parquet vote roster")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--start-year", type=int, default=2011)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()
    print(json.dumps(collect(args.manifest, args.cache, args.ofs,
                             start_year=args.start_year, end_year=args.end_year), indent=2))


if __name__ == "__main__":
    main()
