from pathlib import Path

import pandas as pd

from scripts.build_federal_explanations_snapshot import build_snapshot


def test_build_snapshot_keeps_only_source_specific_tables(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    output = tmp_path / "processed"
    audit.mkdir()

    pd.DataFrame(
        {
            "vote_id": ["6000"],
            "vote_date": ["2020-02-09"],
            "source_id": ["src-1"],
            "pdf_sha256": ["abc"],
            "brochure_status": ["FOUND"],
            "availability_status": ["INVESTIGATE"],
            "match_status": ["UNRESOLVED"],
            "extraction_status": ["EXTRACTED"],
            "semantic_status": ["NOT_VALIDATED"],
            "object_ids": [["src-1-object-1"]],
            "section_count": [1],
            "swissvotes_topic": ["health"],
            "swissvotes_federal_council_position": ["YES"],
            "municipality_id": [5586],
            "yes_share": [0.55],
        }
    ).to_parquet(audit / "coverage.parquet", index=False)

    pd.DataFrame({"source_id": ["src-1"], "vote_date": ["2020-02-09"]}).to_parquet(
        audit / "sources.parquet", index=False
    )
    pd.DataFrame({"source_id": ["src-1"], "page_number": [1], "text": ["x"]}).to_parquet(
        audit / "pages.parquet", index=False
    )
    pd.DataFrame({"source_id": ["src-1"], "object_id": ["o1"], "full_text": ["x"]}).to_parquet(
        audit / "sections.parquet", index=False
    )
    pd.DataFrame({"vote_id": ["6000"], "object_id": ["o1"]}).to_parquet(
        audit / "section_links.parquet", index=False
    )

    written = build_snapshot(audit, output)

    assert {path.name for path in written} == {
        "objects.parquet",
        "sources.parquet",
        "pages.parquet",
        "sections.parquet",
        "section_links.parquet",
    }

    objects = pd.read_parquet(output / "objects.parquet")
    assert "swissvotes_topic" not in objects.columns
    assert "swissvotes_federal_council_position" not in objects.columns
    assert "municipality_id" not in objects.columns
    assert "yes_share" not in objects.columns
    assert list(objects.columns) == [
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
    ]
