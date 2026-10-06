from pathlib import Path

import pandas as pd

from scripts.federal_explanations_eda import generate_eda


def test_generate_eda_from_synthetic_exports(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "eda"
    input_dir.mkdir()

    pd.DataFrame(
        {
            "vote_id": ["6000", "6010", "6020", "6030"],
            "vote_date": ["2020-02-09", "2020-09-27", "2021-03-07", "2021-06-13"],
            "coverage_status": ["FOUND", "FOUND", "FOUND", "MISSING"],
            "exclusion_reasons": ["", "semantic review", "", "no brochure"],
        }
    ).to_parquet(input_dir / "coverage.parquet", index=False)

    pd.DataFrame(
        {
            "section_id": ["s1", "s2", "s3"],
            "vote_date": ["2020-02-09", "2020-09-27", "2021-03-07"],
            "full_text": [
                "A" * 1200,
                "B" * 1800,
                "C" * 900,
            ],
            "extraction_status": ["EXTRACTED", "EXTRACTED", "EXTRACTED"],
        }
    ).to_parquet(input_dir / "sections.parquet", index=False)

    pd.DataFrame(
        {
            "source_id": ["a", "a", "b", "b", "c"],
            "page": [1, 2, 1, 2, 1],
            "method": ["native", "native", "native", "ocr", "native"],
        }
    ).to_parquet(input_dir / "pages.parquet", index=False)

    generated = generate_eda(input_dir, output_dir)

    generated_names = {path.name for path in generated}
    assert generated_names == {
        "coverage_by_year.png",
        "extraction_quality.png",
        "text_length_distribution.png",
        "report.md",
    }
    assert all(path.is_file() for path in generated)

    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "Objets dans le tableau de couverture : **4**" in report
    assert "Objets éligibles : **2**" in report
    assert "`ocr` : **1**" in report
