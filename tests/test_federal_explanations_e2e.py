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


def test_full_period_sections_include_official_fields_and_related_vote_export(tmp_path, monkeypatch):
    import pandas as pd
    import scripts.audit_federal_explanations_period as audit

    ofs = tmp_path / "ofs.csv"
    pd.DataFrame([
        {"vote_id": "420", "vote_date": "2016-02-28", "is_tiebreak_question": False,
         "related_vote_ids": ["421"]},
        {"vote_id": "421", "vote_date": "2016-02-28", "is_tiebreak_question": True,
         "related_vote_ids": []},
    ]).to_csv(ofs, index=False)
    swiss = tmp_path / "swissvotes.csv"
    pd.DataFrame([{"anr": "42", "titel_fr": "Titre fourni"},
                  {"anr": "42.1", "titel_fr": "Second titre"}]).to_csv(swiss, index=False)
    pdf = tmp_path / "brochure.pdf"
    pdf.write_bytes(b"fixture")
    sources = tmp_path / "sources.json"
    sources.write_text(
        '{"documents":[{"source_id":"s1","pdf_path":"' + str(pdf) + '",'
        '"vote_date":"2016-02-28","ofs_vote_ids":["420","421"],'
        '"match_status":"UNRESOLVED"}]}', encoding="utf-8")
    monkeypatch.setattr(audit, "extract_pdf_pages", lambda _path: [{
        "page": 1, "text": "Objet 1: Titre fourni\nRésumé officiel: Résumé déclaré.\n"
        "Conseil fédéral: Le Conseil fédéral et le Parlement vous recommandent de rejeter l’initiative.\n"
        "Objet 2: Titre sans champs",
        "method": "native", "status": "OK",
    }])
    output = tmp_path / "out"
    audit.run_audit(ofs, swiss, sources, output, source_version="fixture")

    sections = pd.read_parquet(output / "sections.parquet")
    section = sections.loc[sections.section_order == 1].iloc[0]
    assert section["summary_official"] == "Résumé déclaré."
    assert section["summary_missing_reason"] is None
    assert section["council_recommendation_raw"].startswith("Le Conseil fédéral")
    assert section["council_recommendation_target"] == "REJECT_INITIATIVE"
    assert section["council_recommendation_reason"] == "clear_single_target"
    assert section["council_recommendation_position"] == "REJECT"
    assert section["council_recommendation_type"] == "INITIATIVE"
    assert section["parliament_recommendation_target"] == "REJECT_INITIATIVE"
    assert section["object_type"] == "INITIATIVE"
    missing = sections.loc[sections.section_order == 2].iloc[0]
    assert pd.isna(missing["summary_official"])
    assert "absent" in missing["summary_missing_reason"]
    assert missing["council_recommendation_reason"] == "not_extracted"

    related = pd.read_parquet(output / "related_votes.parquet")
    assert related.to_dict("records") == [{"vote_id": "420", "related_vote_id": "421"}]
    intermediate = pd.read_parquet(output / "votes_intermediate.parquet")
    assert intermediate.set_index("vote_id").loc["420", "related_vote_ids"] == ["421"]
    assert "related_votes.parquet" in (output / "report.md").read_text(encoding="utf-8")
