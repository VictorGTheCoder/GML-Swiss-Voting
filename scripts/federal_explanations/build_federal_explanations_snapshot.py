"""Build the clean, versionable Federal Council explanations snapshot.

The full audit pipeline may emit technical audit tables and cross-source checks.
This script keeps only the source-specific tables needed by downstream users and
removes Swissvotes/OFS feature leakage from the versioned processed snapshot.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

OBJECT_COLUMNS = [
    "vote_id",
    "vote_date",
    "source_id",
    "pdf_sha256",
    "brochure_status",
    "availability_status",
    "match_status",
    "extraction_status",
    "semantic_status",
    "object_ids",
    "section_count",
    "exclusion_reasons",
]

PASSTHROUGH_TABLES = [
    "sources.parquet",
    "pages.parquet",
    "sections.parquet",
    "section_links.parquet",
]


def build_snapshot(input_dir: Path, output_dir: Path) -> list[Path]:
    coverage_path = input_dir / "coverage.parquet"
    if not coverage_path.is_file():
        raise FileNotFoundError(f"Missing required audit table: {coverage_path}")

    coverage = pd.read_parquet(coverage_path)
    missing = [column for column in OBJECT_COLUMNS if column not in coverage.columns]
    if missing:
        raise ValueError(f"coverage.parquet missing columns: {', '.join(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    objects = coverage[OBJECT_COLUMNS].copy()
    objects.to_parquet(output_dir / "objects.parquet", index=False)
    written.append(output_dir / "objects.parquet")

    for name in PASSTHROUGH_TABLES:
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
        description="Build the clean Federal Council explanations processed snapshot"
    )
    parser.add_argument("--input", type=Path, required=True, help="Full audit output directory")
    parser.add_argument("--output", type=Path, required=True, help="Clean processed snapshot directory")
    args = parser.parse_args()

    for path in build_snapshot(args.input, args.output):
        print(path)


if __name__ == "__main__":
    main()
