"""Download sources and build the validated OFS commune x vote dataset.

OFS PX -> parsing -> audit -> cleaning -> validation -> Parquet.
Swissvotes is cleaned separately. Optional key checks prepare a future join only.
``--with-communes`` also builds the commune reference datasets (communes register, STATPOP,
typologies); the first STATPOP download takes about an hour because of the OFS rate limit.
Use ``--force`` to refresh the sources; cached downloads are otherwise reused.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_pipeline(force: bool = False, prepare_joins: bool = False, with_communes: bool = False) -> None:
    from scripts.integration import prepare_join
    from scripts.ofs_votes import (
        audit_ofs_votes,
        clean_ofs_votes,
        parse_ofs_votes,
        validate_ofs_votes,
    )
    from scripts.ofs_votes.download_ofs_votes import ensure_raw_data
    from scripts.swissvotes import clean_swissvotes
    from scripts.swissvotes.download_swissvotes import download_swissvotes

    ensure_raw_data(force=force)
    download_swissvotes(force=force)
    parse_ofs_votes.main()
    audit_ofs_votes.main()
    clean_ofs_votes.main()
    validate_ofs_votes.main()
    clean_swissvotes.main()
    if prepare_joins:
        prepare_join.main()
    if with_communes:
        run_communes_pipeline(force=force)


def run_communes_pipeline(force: bool = False) -> None:
    """Commune reference datasets: download, convert to Parquet, build commune features."""
    from scripts.repertoire_communes import convert_repertoire_to_parquet
    from scripts.repertoire_communes.download_repertoire import ensure_raw_data as download_repertoire
    from scripts.statpop import build_statpop_features, convert_statpop_to_parquet
    from scripts.statpop.download_statpop import ensure_raw_data as download_statpop
    from scripts.typologies import build_typology_features
    from scripts.typologies.download_typologies import ensure_raw_data as download_typologies

    download_repertoire(force=force)
    download_typologies(force=force)
    download_statpop(force=force)
    convert_repertoire_to_parquet.main()
    convert_statpop_to_parquet.main()
    build_statpop_features.main()
    build_typology_features.main()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare the project datasets")
    parser.add_argument("--force", action="store_true", help="redownload OFS and Swissvotes")
    parser.add_argument("--with-communes", action="store_true", help="also build STATPOP, typologies and communes register data")
    parser.add_argument("--prepare-joins", action="store_true", help="check identifier correspondences only; no merged dataset")
    args = parser.parse_args()

    run_pipeline(force=args.force, prepare_joins=args.prepare_joins, with_communes=args.with_communes)


if __name__ == "__main__":
    # Support both `python scripts/run_pipeline.py` and `python -m scripts.run_pipeline`.
    if __package__ in (None, ""):
        sys.path.insert(0, str(ROOT))
    main()
