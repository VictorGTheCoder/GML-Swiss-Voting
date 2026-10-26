"""Download sources and build the validated OFS commune x vote dataset.

OFS PX -> parsing -> audit -> cleaning -> validation -> Parquet.
Swissvotes is cleaned separately. Optional key checks prepare a future join only.
``--with-communes`` also builds the commune reference datasets (communes register, STATPOP,
typologies); STATPOP uses the complete PX export to avoid the slow batched API.
Use ``--force`` to refresh the sources; cached downloads are otherwise reused.
"""

from __future__ import annotations

import argparse
import json
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
    from scripts.repertoire_communes.download_repertoire import (
        ensure_raw_data as download_repertoire,
    )
    from scripts.statpop import build_statpop_features, convert_statpop_to_parquet
    from scripts.statpop.download_statpop import ensure_raw_data as download_statpop
    from scripts.typologies import build_typology_features
    from scripts.typologies.download_typologies import (
        ensure_raw_data as download_typologies,
    )

    download_repertoire(force=force)
    download_typologies(force=force)
    download_statpop(force=force)
    convert_repertoire_to_parquet.main()
    convert_statpop_to_parquet.main()
    build_statpop_features.main()
    build_typology_features.main()


def run_all(force: bool = False) -> None:
    """Build every source separately, then audit formats and identifier compatibility."""
    from scripts.common.config import INTERIM_DIR, PROCESSED_DIR, RAW_DIR
    from scripts.elections import (
        build_election_features,
        collect_elections_conseil_national,
    )
    from scripts.federal_explanations.audit_federal_explanations import run_audit
    from scripts.federal_explanations.build_federal_explanations_snapshot import (
        build_snapshot,
    )
    from scripts.federal_explanations.collect_federal_explanations import collect
    from scripts.integration import audit_datasets
    from scripts.repertoire_communes import commune_crosswalk

    run_pipeline(force=force, prepare_joins=True, with_communes=True)
    commune_crosswalk.main([])
    collect_elections_conseil_national.main(force=force)
    build_election_features.main()
    manifest = RAW_DIR / "federal_explanations" / "sources.json"
    cache = RAW_DIR / "federal_explanations" / "pdfs"
    ofs = PROCESSED_DIR / "ofs-votes" / "votes_communes.parquet"
    if force or not manifest.is_file() or json.loads(manifest.read_text(encoding="utf-8")).get("period") != "1978-01-01/2026-12-31":
        collect(manifest, cache, ofs, start_year=1978)
    source_output = INTERIM_DIR / "federal_explanations"
    run_audit(ofs, manifest, source_output, workers=4)
    build_snapshot(source_output, PROCESSED_DIR / "federal_explanations")
    audit_datasets.main()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and prepare the project datasets")
    parser.add_argument("--force", action="store_true", help="redownload OFS and Swissvotes")
    parser.add_argument("--with-communes", action="store_true", help="also build STATPOP, typologies and communes register data")
    parser.add_argument("--prepare-joins", action="store_true", help="check identifier correspondences only; no merged dataset")
    parser.add_argument("--all", action="store_true", help="build all sources, including elections and brochures, then audit compatibility")
    args = parser.parse_args()

    if args.all:
        run_all(force=args.force)
    else:
        run_pipeline(force=args.force, prepare_joins=args.prepare_joins, with_communes=args.with_communes)


if __name__ == "__main__":
    # Support both `python scripts/run_pipeline.py` and `python -m scripts.run_pipeline`.
    if __package__ in (None, ""):
        sys.path.insert(0, str(ROOT))
    main()
