"""Publish the clean, versionable Federal Council explanations snapshot.

The full audit pipeline emits technical audit tables and cross-source checks.
The shared processed snapshot keeps only source-specific Chancellery tables.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


SNAPSHOT_TABLES = [
    "sources.parquet",
    "pages.parquet",
    "sections.parquet",
    "section_links.parquet",
]


def build_snapshot(input_dir: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for name in SNAPSHOT_TABLES:
        source = input_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"Missing required audit table: {source}")

        frame = pd.read_parquet(source)
        destination = output_dir / name
        frame.to_parquet(destination, index=False)
        written.append(destination)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish the clean Federal Council explanations processed snapshot"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    for path in build_snapshot(args.input, args.output):
        print(path)


if __name__ == "__main__":
    main()
