"""Download the OFS federal vote results cube (px-x-1703030000_101) into data/raw/.

Source: Office fédéral de la statistique (OFS/BFS), "Votations populaires (résultats
au niveau des communes depuis 1960)". The complete cube is fetched as a PX file from
PXWeb's file download endpoint (see votes_config.DOWNLOAD_URL). The PXWeb JSON API
is not used: the FSO firewall rejects POST queries that large (~8.5M values).

An existing file is never replaced unless --force is given. A provenance sidecar
(<table>.provenance.json) records URL, retrieval time, size, SHA-256 and the cube's
own LAST-UPDATED stamp.

Usage: python scripts/download_votes.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from parse_votes import read_px_metadata
from votes_config import (
    DATASET_NAME_FR, DOWNLOAD_URL, OFS_TABLE_ID, PROVENANCE_PATH, RAW_PX_PATH, ROOT, SOURCE_PAGE_URL,
)

TIMEOUT_SECONDS = 600


def download(url: str, destination: Path) -> None:
    """Stream to a temporary file and rename only once the payload looks like a PX cube."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    handle.write(chunk)
        head = partial.read_bytes()[:200].decode("utf-8-sig", errors="replace")
        if "AXIS-VERSION" not in head and "CHARSET" not in head:
            raise RuntimeError(f"Response from {url} is not a PX file (starts with {head[:80]!r})")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def write_provenance(px_path: Path, provenance_path: Path, url: str) -> dict:
    content = px_path.read_bytes()
    meta = read_px_metadata(px_path)
    provenance = {
        "source": "Office fédéral de la statistique (OFS)",
        "dataset": DATASET_NAME_FR,
        "ofs_table_id": OFS_TABLE_ID,
        "source_page": SOURCE_PAGE_URL,
        "download_url": url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file": px_path.relative_to(ROOT).as_posix(),
        "format": "PC-Axis (.px), UTF-8 with BOM despite CODEPAGE header",
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "px_matrix": meta.get("MATRIX", [""])[0],
        "px_last_updated": meta.get("LAST-UPDATED", [""])[0],
        "px_creation_date": meta.get("CREATION-DATE", [""])[0],
        "script": "scripts/download_votes.py",
    }
    if provenance["px_matrix"] != OFS_TABLE_ID:
        raise RuntimeError(f"Downloaded cube is {provenance['px_matrix']!r}, expected {OFS_TABLE_ID}")
    provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return provenance


def ensure_raw_data(force: bool = False) -> Path:
    if RAW_PX_PATH.exists() and not force:
        print(f"Raw file already present, not re-downloading: {RAW_PX_PATH} (use --force to replace)")
        if not PROVENANCE_PATH.exists():
            print(f"Warning: {PROVENANCE_PATH.name} missing; provenance of the existing file is unknown", file=sys.stderr)
        return RAW_PX_PATH
    print(f"Downloading {DOWNLOAD_URL} ...")
    download(DOWNLOAD_URL, RAW_PX_PATH)
    provenance = write_provenance(RAW_PX_PATH, PROVENANCE_PATH, DOWNLOAD_URL)
    print(f"Saved {provenance['bytes']:,} bytes to {RAW_PX_PATH}")
    print(f"Cube LAST-UPDATED {provenance['px_last_updated']}, provenance in {PROVENANCE_PATH}")
    return RAW_PX_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="replace an existing raw file")
    args = parser.parse_args()
    try:
        ensure_raw_data(force=args.force)
    except (requests.RequestException, RuntimeError) as error:
        raise SystemExit(f"Download failed: {error}") from error


if __name__ == "__main__":
    main()
