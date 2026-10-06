from pathlib import Path

import pandas as pd

from scripts.build_federal_explanations_snapshot import build_snapshot


def test_build_snapshot_keeps_only_source_specific_tables(tmp_path: Path) -> None:
    audit = tmp_path / "audit"
    output = tmp_path / "processed"
    audit.mkdir()

    pd.DataFrame({"source_id": ["src-1"], "vote_date": ["2020-02-09"]}).to_parquet(
        audit / "sources.parquet", index=False
    )
    pd.DataFrame(
        {"source_id": ["src-1"], "page_number": [1], "text": ["x"], "method": ["native"]}
    ).to_parquet(audit / "pages.parquet", index=False)
    pd.DataFrame(
        {"source_id": ["src-1"], "object_id": ["o1"], "full_text": ["x"]}
    ).to_parquet(audit / "sections.parquet", index=False)
    pd.DataFrame(
        {"vote_id": ["6000"], "object_id": ["o1"], "source_id": ["src-1"]}
    ).to_parquet(audit / "section_links.parquet", index=False)

    written = build_snapshot(audit, output)

    assert {path.name for path in written} == {
        "sources.parquet",
        "pages.parquet",
        "sections.parquet",
        "section_links.parquet",
    }
    assert {path.name for path in output.iterdir()} == {
        "sources.parquet",
        "pages.parquet",
        "sections.parquet",
        "section_links.parquet",
    }
