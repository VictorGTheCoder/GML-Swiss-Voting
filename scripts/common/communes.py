"""Shared paths, constants and download helpers for the commune reference datasets.

Used by the scripts of scripts/repertoire_communes/, scripts/statpop/ and scripts/typologies/ (all data from the
Office fédéral de la statistique, OFS/BFS). Downloads never replace an existing file unless
--force is given, and each one is recorded in a provenance.json next to the file (URL,
retrieval time, size and SHA-256).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from scripts.common.config import INTERIM_DIR, PROCESSED_DIR, RAW_DIR, REPORTS_DIR, ROOT

# One folder per dataset at every stage, named like its scripts package.
REGISTER_RAW_DIR = RAW_DIR / "repertoire_communes"
STATPOP_RAW_DIR = RAW_DIR / "statpop"
TYPOLOGIES_RAW_DIR = RAW_DIR / "typologies"
REGISTER_INTERIM_DIR = INTERIM_DIR / "repertoire_communes"
STATPOP_INTERIM_DIR = INTERIM_DIR / "statpop"
REGISTER_PROCESSED_DIR = PROCESSED_DIR / "repertoire_communes"
STATPOP_PROCESSED_DIR = PROCESSED_DIR / "statpop"
TYPOLOGIES_PROCESSED_DIR = PROCESSED_DIR / "typologies"
REGISTER_REPORTS_DIR = REPORTS_DIR / "datasets" / "repertoire_communes"
PROVENANCE_NAME = "provenance.json"

AGVCH_BASE = "https://www.agvchapp.bfs.admin.ch"
REFERENCE_DATE = date(2026, 1, 1)  # commune geography used by the vote results

TIMEOUT_SECONDS = 300
MAX_RETRIES = 6
PAUSE_SECONDS = 3  # PXWeb answers 429 when queries come too fast


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def record_provenance(key: str, path: Path, url: str, **extra) -> None:
    content = path.read_bytes()
    provenance_path = path.parent / PROVENANCE_NAME
    provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else {}
    provenance[key] = {
        "source": "Office fédéral de la statistique (OFS)",
        "url": url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file": path.relative_to(ROOT).as_posix(),
        "bytes": len(content),
        "sha256": sha256(content),
        **extra,
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def should_skip(path: Path, force: bool) -> bool:
    if path.exists() and not force:
        print(f"Already present, skipping: {path.relative_to(ROOT)} (use --force to replace)")
        return True
    return False


def request_with_retry(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    """Retry on 429/5xx and transient connection errors with exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            response = session.request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as error:
            if attempt == MAX_RETRIES - 1:
                raise
            print(f"  {type(error).__name__} for {url}, retrying in {10 * 2**attempt}s")
        else:
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response
            print(f"  HTTP {response.status_code} from {url}, retrying in {10 * 2**attempt}s")
        time.sleep(10 * 2**attempt)
    response.raise_for_status()
    return response


def write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_bytes(content)
    partial.replace(path)


def fr_date(day: date) -> str:
    return day.strftime("%d-%m-%Y")
