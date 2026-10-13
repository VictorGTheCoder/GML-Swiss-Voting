"""Download sources and build the validated OFS commune x vote dataset.

OFS PX -> parsing -> audit -> cleaning -> validation -> Parquet.
Swissvotes is cleaned and the exact join keys are checked against the OFS results.
Use ``--force`` to refresh both sources; cached downloads are otherwise reused.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_pipeline(force: bool = False) -> None:
    from scripts import prepare_join
    from scripts.cleaning import (
        audit_ofs_votes,
        clean_ofs_votes,
        clean_swissvotes,
        parse_ofs_votes,
        validate_ofs_votes,
    )
    from scripts.download.download_ofs_votes import ensure_raw_data
    from scripts.download.download_swissvotes import download_swissvotes

    ensure_raw_data(force=force)
    download_swissvotes(force=force)
    parse_ofs_votes.main()
    audit_ofs_votes.main()
    clean_ofs_votes.main()
    validate_ofs_votes.main()
    clean_swissvotes.main()
    prepare_join.main()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare the project datasets")
    parser.add_argument("--force", action="store_true", help="redownload OFS and Swissvotes")
    args = parser.parse_args()

    run_pipeline(force=args.force)


if __name__ == "__main__":
    # Support both `python scripts/run_pipeline.py` and `python -m scripts.run_pipeline`.
    if __package__ in (None, ""):
        sys.path.insert(0, str(ROOT))
    main()
