import pandas as pd
import hashlib
import json

from scripts.integration.modeling_objects import (
    build_object_feature_block,
    load_swissvotes_source,
    object_history_domains,
)
from scripts.integration.modeling_temporal import prepare_modeling_table


def outcomes():
    return pd.DataFrame([
        {"municipality_id": "1", "vote_id": "10", "vote_date": "2018-03-04",
         "votes_yes": 30, "votes_no": 70, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "2", "vote_id": "10", "vote_date": "2018-03-04",
         "votes_yes": 3, "votes_no": 7, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
        {"municipality_id": "2", "vote_id": "11", "vote_date": "2018-03-04",
         "votes_yes": 60, "votes_no": 40, "is_special_unit": False,
         "is_tiebreak_question": False, "is_provisional": False},
    ])


def metadata():
    return pd.DataFrame([
        {"anr": "1.0", "datum": "04.03.2018", "rechtsform": "1",
         "d1e1": "1", "d2e1": "2", "d3e1": "2"},
        {"anr": "1.1", "datum": "04.03.2018", "rechtsform": "4",
         "d1e1": "3", "d2e1": ".", "d3e1": "."},
    ])


def publications():
    return pd.DataFrame([
        {"vote_id": "10", "forecast_at": "2018-02-01T00:00:00Z",
         "forecast_source": "fixture", "forecast_source_version": "v1",
         "forecast_evidence": "fixture:brochure-10"},
        {"vote_id": "11", "forecast_at": "2018-02-01T00:00:00Z",
         "forecast_source": "fixture", "forecast_source_version": "v1",
         "forecast_evidence": "fixture:brochure-11"},
    ])


def test_complete_preparation_attaches_all_domains_as_indicators_and_history_membership():
    result = build_object_feature_block(
        outcomes(), metadata(), source_version="swissvotes-fixture-v1",
        source_url="https://example.test/swissvotes",
        published_at="2018-01-01T00:00:00Z", publication_evidence="fixture release",
        reference_date="2018-01-01T00:00:00Z",
    )
    prepared = prepare_modeling_table(
        outcomes(), geography_id="fixture-g1", source_version="ofs-fixture-v1",
        forecast_publications=publications(), result_publications=None,
        feature_blocks=(result.feature_block,),
    )

    first = prepared.prepared.loc[lambda rows: rows.vote_id.eq("10")].iloc[0]
    assert first["swissvotes__legal_form"] == "mandatory_referendum"
    assert first["swissvotes__policy_domain_01"] == 1
    assert first["swissvotes__policy_domain_02"] == 1
    assert first["swissvotes__policy_domain_03"] == 0
    assert first["swissvotes__policy_domain_04"] == 0
    second = prepared.prepared.loc[lambda rows: rows.vote_id.eq("11")].iloc[0]
    assert second["swissvotes__legal_form"] == "direct_counterproposal"
    assert second["swissvotes__policy_domain_03"] == 1
    assert second["swissvotes__policy_domain_02"] == 0
    assert len(prepared.prepared) == 3
    assert len(prepared.strict_population) == 3
    assert prepared.prepared.query("vote_id == '10'")["swissvotes__policy_domain_02"].tolist() == [1, 1]
    assert result.domain_metadata.set_index("vote_id").loc["10", "domain_codes"] == (1, 2)
    assert object_history_domains(result.domain_metadata).set_index("vote_id").loc["10", "domain_codes"] == (1, 2)
    assert set(result.feature_block.numeric_features) == {
        f"policy_domain_{number:02d}" for number in range(1, 13)
    }
    assert result.feature_block.categorical_features == ("legal_form",)


def test_unknown_or_inconsistent_metadata_stays_auditable_without_multiplying_rows():
    contradictory = metadata()
    contradictory.loc[0, "datum"] = "05.03.2018"
    duplicate = pd.concat([metadata(), metadata().iloc[[0]]], ignore_index=True)
    unknown_domain = metadata().iloc[[0]].copy()
    unknown_domain.loc[:, ["d1e1", "d2e1", "d3e1"]] = "."

    for source, expected in (
        (contradictory, "date_mismatch"),
        (duplicate, "duplicate_swissvotes_key"),
    ):
        result = build_object_feature_block(
            outcomes(), source, source_version="swissvotes-fixture-v1",
            source_url="https://example.test/swissvotes",
        )
        assert len(result.feature_block.records.query("vote_id == '10'")) == 1
        assert result.join_audit.set_index("vote_id").loc["10", "join_status"] == expected
        assert pd.isna(result.feature_block.records.set_index("vote_id").loc["10", "policy_domain_01"])

    result = build_object_feature_block(
        outcomes().iloc[[0]], unknown_domain, source_version="swissvotes-fixture-v1",
        source_url="https://example.test/swissvotes",
    )
    values = result.feature_block.records.filter(regex=r"^policy_domain_").iloc[0]
    assert values.isna().all()
    assert result.domain_metadata.iloc[0].domain_status == "unknown_classification"


def test_exact_keys_reject_date_only_match_and_unknown_release_fails_strict_gate():
    source = metadata().iloc[[0]].copy()
    source.loc[:, "anr"] = "999.0"
    result = build_object_feature_block(
        outcomes().iloc[[0]], source, source_version="swissvotes-fixture-v1",
        source_url="https://example.test/swissvotes",
    )
    prepared = prepare_modeling_table(
        outcomes().iloc[[0]], geography_id="fixture-g1", source_version="ofs-fixture-v1",
        forecast_publications=publications().iloc[[0]], feature_blocks=(result.feature_block,),
    )
    assert len(prepared.prepared) == 1
    assert pd.isna(prepared.prepared.iloc[0]["swissvotes__policy_domain_01"])
    assert prepared.prepared.iloc[0]["swissvotes__availability_status"] == "unknown_availability"
    assert prepared.strict_population.empty
    assert prepared.exclusions.reason.eq("feature_unknown_availability").any()


def test_subsidiary_question_keeps_legal_form_categorical_but_stays_out_of_strict_population():
    target = outcomes().iloc[[0]].copy()
    target["is_tiebreak_question"] = True
    subsidiary = metadata().iloc[[0]].copy()
    subsidiary["rechtsform"] = "5"
    result = build_object_feature_block(
        target, subsidiary, source_version="swissvotes-fixture-v1",
        source_url="https://example.test/swissvotes",
        published_at="2018-01-01T00:00:00Z", publication_evidence="fixture release",
        reference_date="2018-01-01T00:00:00Z",
    )
    prepared = prepare_modeling_table(
        target, geography_id="fixture-g1", source_version="ofs-fixture-v1",
        forecast_publications=publications().iloc[[0]], feature_blocks=(result.feature_block,),
    )

    assert pd.isna(prepared.prepared.iloc[0]["swissvotes__legal_form"])
    assert prepared.prepared.iloc[0].is_subsidiary
    assert prepared.strict_population.empty


def test_local_csv_loader_checks_sidecar_hash_and_preserves_swissvotes_identifiers(tmp_path):
    source_dir = tmp_path / "raw" / "features"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "swissvotes_dataset.csv"
    source_path.write_text(
        "anr,datum,rechtsform,d1e1,d2e1,d3e1\n1.1,04.03.2018,4,3,.,.\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    source_path.with_suffix(".provenance.json").write_text(json.dumps({
        "source": "https://example.test/swissvotes.csv",
        "retrieved_at_utc": "2026-10-06T12:00:00Z",
        "sha256": digest,
    }), encoding="utf-8")

    source = load_swissvotes_source(tmp_path)
    assert source.records.iloc[0].anr == "1.1"
    assert source.source_version == f"sha256:{digest}"
    assert source.sha256 == digest
