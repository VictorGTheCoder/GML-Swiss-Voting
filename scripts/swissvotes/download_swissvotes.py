"""Download the Swissvotes dataset independently of the OFS results.

Usage: python -m scripts.swissvotes.download_swissvotes [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from scripts.common.config import SWISSVOTES_PATH, SWISSVOTES_URL


def download_swissvotes(force: bool = False, output: Path = SWISSVOTES_PATH) -> Path:
    if output.exists() and not force:
        print(f"Already present: {output} (use --force to replace)")
        return output
    response = requests.get(SWISSVOTES_URL, timeout=60)
    response.raise_for_status()
    # Swissvotes publishes a semicolon-delimited UTF-8 CSV.
    frame = pd.read_csv(io.BytesIO(response.content), sep=";", encoding="utf-8-sig",
                        dtype=str, keep_default_na=False)
    if frame.empty or not {"anr", "datum"}.issubset(frame.columns):
        raise ValueError("Invalid or empty Swissvotes CSV response")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".part")
    try:
        partial.write_bytes(response.content)
        partial.replace(output)
    finally:
        partial.unlink(missing_ok=True)
    provenance = {
        "source": "Swissvotes",
        "url": SWISSVOTES_URL,
        "script": "scripts/swissvotes/download_swissvotes.py",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": len(response.content),
        "sha256": hashlib.sha256(response.content).hexdigest(),
    }
    output.with_suffix(".provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Downloaded: {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="replace an existing raw file")
    args = parser.parse_args()
    download_swissvotes(force=args.force)


if __name__ == "__main__":
    main()
