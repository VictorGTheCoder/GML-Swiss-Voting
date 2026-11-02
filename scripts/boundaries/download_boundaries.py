"""Download the swisstopo swissBOUNDARIES3D commune polygons into data/raw/boundaries/.

Edition matching the commune geography of the vote results (REFERENCE_DATE). Used only to draw
maps (scripts.integration.presentation_figures); not a model input.

Usage: python -m scripts.boundaries.download_boundaries [--force]
"""

from __future__ import annotations

import argparse
import zipfile

import requests

from scripts.common.communes import (
    REFERENCE_DATE,
    ROOT,
    record_provenance,
    request_with_retry,
    should_skip,
    write_atomic,
)
from scripts.common.config import RAW_DIR

EDITION = f"swissboundaries3d_{REFERENCE_DATE:%Y-%m}"
BOUNDARIES_RAW_DIR = RAW_DIR / "boundaries" / EDITION
EXTRACTED_DIR = BOUNDARIES_RAW_DIR / "extracted"
URL = f"https://data.geo.admin.ch/ch.swisstopo.swissboundaries3d/{EDITION}/{EDITION}_2056_5728.shp.zip"


def download_boundaries(session: requests.Session, force: bool) -> None:
    path = BOUNDARIES_RAW_DIR / "boundaries.zip"
    if not should_skip(path, force):
        response = request_with_retry(session, "GET", URL)
        write_atomic(path, response.content)
        if not zipfile.is_zipfile(path):
            path.unlink()
            raise RuntimeError("Boundaries download is not a zip file")
        record_provenance(EDITION, path, URL, source="swisstopo (swissBOUNDARIES3D)")
        print(f"Saved {path.relative_to(ROOT)} ({len(response.content):,} bytes)")
    if force or not EXTRACTED_DIR.exists():
        with zipfile.ZipFile(path) as archive:
            archive.extractall(EXTRACTED_DIR)


def ensure_raw_data(force: bool = False) -> None:
    """Download the raw files that are missing (all of them with ``force``); used by run_pipeline."""
    download_boundaries(requests.Session(), force)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="replace the existing raw file")
    args = parser.parse_args()
    try:
        ensure_raw_data(args.force)
    except (requests.RequestException, RuntimeError) as error:
        raise SystemExit(f"Boundaries download failed: {error}") from error


if __name__ == "__main__":
    main()
