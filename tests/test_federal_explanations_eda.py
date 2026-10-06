from pathlib import Path

import pandas as pd

from scripts.federal_explanations_eda import generate_eda


def test_generate_eda_from_synthetic_exports(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "eda"
    input_dir.mkdir()

    pd.DataFrame(
        {
            "source_id": ["src-a", "src-b", "src-c"],
            "vote_date": ["2020-02-09", "2020-09-27", "2021-03-07"],
        }
    ).to_parquet(input_dir / "sources.parquet", index=False)

    pd.DataFrame(
        {
            "object_id": ["s1", "s2", "s3"],
            "full_text": ["A" * 1200, "B" * 1800, "C" * 900],
        }
    ).to_parquet(input_dir / "sections.parquet", index=False)

    pd.DataFrame(
        {
            "source_id": ["src-a", "src-a", "src-b", "src-b", "src-c"],
            "page_number": [1, 2, 1, 2, 1],
            "method": ["native", "native", "native", "ocr", "native"],
        }
    ).to_parquet(input_dir / "pages.parquet", index=False)

    pd.DataFrame(
        {
            "vote_id": ["6000", "6010", "6020", "6030"],
            "object_id": ["s1", "s2", "s3", "s3"],
            "source_id": ["src-a", "src-b", "src-c", "src-c"],
        }
    ).to_parquet(input_dir / "section_links.parquet", index=False)

    generated = generate_eda(input_dir, output_dir)

    assert {path.name for path in generated} == {
        "coverage_by_year.png",
        "extraction_quality.png",
        "text_length_distribution.png",
        "report.md",
    }

    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "Brochures : **3**" in report
    assert "Objets OFS reliés au corpus : **4**" in report
    assert "ocr : **1**" in report
