def test_model_export_requires_explicit_semantic_validation():
    from scripts.federal_explanations.federal_explanations_temporal import (
        filter_model_eligible,
    )

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

    from scripts.federal_explanations.audit_federal_explanations import run_audit

    ofs = tmp_path / "ofs.csv"
    pd.DataFrame([
        {"vote_id": "420", "vote_date": "2016-02-28", "is_tiebreak_question": False,
         "municipality_id": municipality, "votes_yes": 123, "yes_share": 0.5}
        for municipality in ("0001", "0002")
    ]).to_csv(ofs, index=False)
    swiss = tmp_path / "swissvotes.csv"
    pd.DataFrame([{"anr": "42", "titel_fr": "Titre fourni"}]).to_csv(swiss, index=False)
    sources = tmp_path / "sources.json"
    sources.write_text('{"documents": []}', encoding="utf-8")
    output = tmp_path / "out"
    run_audit(ofs, sources, output)
    coverage = pd.read_parquet(output / "coverage.parquet")
    assert len(coverage) == 1
    assert not any(c.startswith("swissvotes_") for c in coverage.columns)
    assert not {"municipality_id", "votes_yes", "yes_share"} & set(coverage.columns)
    assert coverage.loc[0, "brochure_status"] == "MISSING_OR_AMBIGUOUS"
    assert not (output / "model.parquet").exists()
    assert not pd.read_parquet(output / "link_eligibility.parquet")["eligible"].any()
    links = pd.read_parquet(output / "section_links.parquet")
    assert links.empty
    assert "OFS brochure correspondence is not validated" in coverage.loc[0, "exclusion_reasons"]
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "no French Chancellerie brochure" in report


def test_full_period_sections_include_official_fields_and_related_vote_export(tmp_path, monkeypatch):
    import json

    import pandas as pd

    from scripts.federal_explanations import audit_federal_explanations as audit


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
        json.dumps({"documents": [{
            "source_id": "s1", "pdf_path": str(pdf),
            "vote_date": "2016-02-28", "ofs_vote_ids": ["420", "421"],
            "match_status": "UNRESOLVED",
        }]}), encoding="utf-8")
    monkeypatch.setattr(audit, "extract_pdf_pages", lambda _path: [{
        "page": 1, "text": "Objet 1: Titre fourni\nRésumé officiel: Résumé déclaré.\n"
        "Conseil fédéral: Le Conseil fédéral et le Parlement vous recommandent de rejeter l’initiative.\n"
        "Objet 2: Titre sans champs",
        "method": "native", "status": "OK",
    }])
    output = tmp_path / "out"
    audit.run_audit(ofs, sources, output)

    sections = pd.read_parquet(output / "sections.parquet")
    section = sections.loc[sections.section_order == 1].iloc[0]
    assert section["summary_official"] == "Résumé déclaré."
    assert pd.isna(section["summary_missing_reason"])
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
    assert not (output / "votes_intermediate.parquet").exists()
    assert "related_votes.parquet" in (output / "report.md").read_text(encoding="utf-8")
