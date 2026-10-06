from scripts.federal_explanations_swissvotes import join_swissvotes


def test_swissvotes_uses_exact_anr_and_reports_missing_and_duplicate_ids():
    ofs = [
        {"vote_id": "10", "vote_date": "2020-01-01"},
        {"vote_id": "20", "vote_date": "2020-01-01"},
    ]
    rows = [
        {"anr": "1", "titel_fr": "Exact"},
        {"anr": "2", "titel_fr": "Unique second"},
        {"anr": "1", "titel_fr": "Duplicate"},
        {"anr": "999", "titel_fr": "Unknown"},
    ]
    result = join_swissvotes(ofs, rows, source_version="2026-10-01", source_sha256="abc", license="CC BY 4.0")
    by_id = {item["vote_id"]: item for item in result["votes"]}
    assert by_id["10"]["swissvotes_status"] == "DUPLICATE_ANR"
    assert by_id["10"]["swissvotes_anr_raw_candidates"] == ["1", "1"]
    assert by_id["20"]["swissvotes_status"] == "MATCHED"
    assert by_id["20"]["swissvotes_anr_vote_id"] == "20"
    assert result["unmatched_swissvotes"] == ["9990"]


def test_swissvotes_metadata_has_explicit_source_provenance():
    result = join_swissvotes(
        [{"vote_id": "10"}], [{"anr": "1", "titel_fr": "Titre", "typ_fr": "Initiative"}],
        source_version="2026-10-01", source_sha256="abc", license="CC BY 4.0",
    )
    vote = result["votes"][0]
    assert vote["swissvotes_title_fr"] == "Titre"
    assert vote["swissvotes_legal_form_fr"] == "Initiative"
    assert vote["swissvotes_provenance"]["license"] == "CC BY 4.0"
    assert vote["swissvotes_provenance"]["source_sha256"] == "abc"
    assert vote["brochure_source"] is None


def test_swissvotes_decimal_encoding_is_date_checked_and_preserves_raw_anr():
    result = join_swissvotes(
        [{"vote_id": "6821", "vote_date": "2026-06-14"}, {"vote_id": "6822", "vote_date": "2026-06-14"}],
        [{"anr": "682.1", "datum": "14.06.2026", "titel_off_f": "First"},
         {"anr": "682.2", "datum": "15.06.2026", "titel_off_f": "Wrong date"},
         {"anr": "not-a-number", "titel_off_f": "Invalid"}],
        source_version="fixture", source_sha256="abc", license="CC BY 4.0",
    )
    by_id = {row["vote_id"]: row for row in result["votes"]}
    assert by_id["6821"]["swissvotes_status"] == "MATCHED"
    assert by_id["6821"]["swissvotes_anr_raw"] == "682.1"
    assert by_id["6822"]["swissvotes_status"] == "DATE_MISMATCH"
    assert by_id["6822"]["swissvotes_title_fr"] is None
    assert "date" in by_id["6822"]["field_missing_reasons"]["swissvotes_title_fr"].lower()
    assert result["unconvertible_anr"] == ["not-a-number"]


def test_model_export_requires_explicit_semantic_validation():
    from scripts.federal_explanations_temporal import filter_model_eligible

    row = {
        "vote_id": "1", "availability_status": "CONFIRMED_PRE_VOTE",
        "source_sha256": "a" * 64, "decision_source_sha256": "a" * 64,
        "match_status": "VALIDATED", "extraction_status": "EXTRACTED",
        "semantic_status": "NOT_VALIDATED", "is_tiebreak_question": False,
    }
    eligible, excluded = filter_model_eligible([row])
    assert eligible == []
    assert "semantic" in excluded[0]["exclusion_reason"]
    row["semantic_status"] = "VALIDATED"
    eligible, _ = filter_model_eligible([row])
    assert [item["vote_id"] for item in eligible] == ["1"]


def test_full_period_audit_keeps_missing_brochure_rows_and_empty_model(tmp_path):
    import pandas as pd
    from scripts.audit_federal_explanations_period import run_audit

    ofs = tmp_path / "ofs.csv"
    pd.DataFrame([{"vote_id": "420", "vote_date": "2016-02-28", "is_tiebreak_question": False}]).to_csv(ofs, index=False)
    swiss = tmp_path / "swissvotes.csv"
    pd.DataFrame([{"anr": "42", "titel_fr": "Titre fourni"}]).to_csv(swiss, index=False)
    sources = tmp_path / "sources.json"
    sources.write_text('{"documents": []}', encoding="utf-8")
    output = tmp_path / "out"
    run_audit(ofs, swiss, sources, output, source_version="fixture")
    coverage = pd.read_parquet(output / "coverage.parquet")
    assert len(coverage) == 1
    assert coverage.loc[0, "swissvotes_title_fr"] == "Titre fourni"
    assert coverage.loc[0, "brochure_status"] == "MISSING_OR_AMBIGUOUS"
    assert pd.read_parquet(output / "model.parquet").empty
    links = pd.read_parquet(output / "section_links.parquet")
    assert links.empty
    assert "OFS brochure correspondence is not validated" in coverage.loc[0, "exclusion_reasons"]
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "no French Chancellerie brochure" in report
