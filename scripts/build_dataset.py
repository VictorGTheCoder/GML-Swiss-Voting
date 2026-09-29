"""Rebuild the commune x vote dataset from scratch, in order:

1. download the OFS cube if data/raw has no copy (--force-download to refresh)
2. parse it into a lossless long table            -> data/interim/votes_all_levels.parquet
3. audit the raw table                            -> reports/data_audit.md
4. clean (every removal logged)                   -> reports/cleaning_log.md
5. validate (aborts on any "error" check)         -> reports/validation_report.md
6. write the processed dataset                    -> data/processed/votes_communes.parquet

Usage: python scripts/build_dataset.py [--force-download]
"""

from __future__ import annotations

import argparse

import requests

from audit_votes import AUDIT_PATH, build_audit
from clean_votes import CLEAN_PATH, CLEANING_LOG_PATH, clean_votes, parse_provisional_months
from download_votes import ensure_raw_data
from parse_votes import px_to_long, read_px
from validate_votes import VALIDATION_REPORT_PATH, ValidationError, assert_valid, checks_to_markdown, run_checks
from votes_config import INTERIM_PATH, PROCESSED_PATH, REPORTS_DIR


def build(force_download: bool = False) -> None:
    px_path = ensure_raw_data(force=force_download)

    print("Parsing PX cube ...")
    px = read_px(px_path)
    frame = px_to_long(px)
    INTERIM_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(INTERIM_PATH, index=False)
    print(f"  {len(frame):,} location x vote rows -> {INTERIM_PATH}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(build_audit(frame, px.metadata), encoding="utf-8")
    print(f"  audit -> {AUDIT_PATH}")

    months = parse_provisional_months("".join(px.metadata.get("NOTE[fr]", [])))
    if not months:
        print("  warning: no provisional results found in the OFS note; is_provisional is all False")
    clean, log = clean_votes(frame, months)
    clean.to_parquet(CLEAN_PATH, index=False)
    CLEANING_LOG_PATH.write_text("# Cleaning log\n\n" + log.to_markdown() + "\n", encoding="utf-8")
    print(f"  cleaning log -> {CLEANING_LOG_PATH}\n{log.to_markdown()}")

    checks = run_checks(clean)
    VALIDATION_REPORT_PATH.write_text(checks_to_markdown(checks, len(clean)), encoding="utf-8")
    print(f"  validation -> {VALIDATION_REPORT_PATH}")
    for check in checks:
        if not check.passed:
            print(f"    [{check.severity}] {check.name}: {check.n_failed} rows")
    assert_valid(checks)

    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(PROCESSED_PATH, index=False)
    print(f"Done: {len(clean):,} rows, {clean['vote_id'].nunique()} vote objects, "
          f"{clean['municipality_id'].nunique()} units -> {PROCESSED_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the OFS commune x vote dataset")
    parser.add_argument("--force-download", action="store_true", help="re-download even if data/raw has a copy")
    args = parser.parse_args()
    try:
        build(force_download=args.force_download)
    except ValidationError as error:
        raise SystemExit(f"Validation failed, processed dataset NOT written: {error}") from error
    except (requests.RequestException, RuntimeError) as error:
        raise SystemExit(f"Download failed: {error}") from error


if __name__ == "__main__":
    main()
