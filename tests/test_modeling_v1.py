"""The complete V1 preparation/export seam, using documentary fixture sources."""
import json

import pandas as pd
import pytest

from scripts.integration.modeling_objects import build_object_feature_block
from scripts.integration.modeling_v1 import prepare_v1_table, write_v1_artifacts
from scripts.modeling.feature_blocks import FeatureBlock


def fixture_sources():
    outcomes = pd.DataFrame([
        {"municipality_id": "1", "vote_id": "10", "vote_date": "2018-03-04",
             "votes_yes": 30, "votes_no": 70, "is_special_unit": False,
             "is_tiebreak_question": False, "is_provisional": False},
    ])
    swissvotes = pd.DataFrame([{"anr": "1.0", "datum": "04.03.2018", "rechtsform": "1",
                                   "d1e1": "1", "d2e1": ".", "d3e1": "."}])
    objects = build_object_feature_block(outcomes, swissvotes, source_version="fixture-swissvotes")
    municipal = FeatureBlock(
        block_id="municipal", scope="municipality",
        records=pd.DataFrame([{
            "municipality_id": "1", "geography_id": "fixture-g1", "reference_date": "2016-12-31",
            "published_at": None, "availability_status": "unknown", "availability_evidence": None,
            "source_version": "fixture-municipal", "population_total": 100, "share_foreign": .2,
            "share_age_0_19": .25, "share_age_20_39": .3, "share_age_65_plus": .15,
            "canton": "VD", "language_region": "French", "urban_rural_type": "rural",
        }]),
        numeric_features=("population_total", "share_foreign", "share_age_0_19",
                          "share_age_20_39", "share_age_65_plus"),
        categorical_features=("canton", "language_region", "urban_rural_type"),
        definitions=dict.fromkeys(("population_total", "share_foreign", "share_age_0_19", "share_age_20_39", "share_age_65_plus", "canton", "language_region", "urban_rural_type"), "fixture definition"),
        source_version="fixture-municipal", source_url="https://example.test/fixture",
        geography_mode="retrospective_fixed",
    )
    return outcomes, objects, (municipal,)


def test_complete_v1_retains_thirty_candidates_and_exports_honest_empty_readiness(tmp_path):
    outcomes, objects, municipal = fixture_sources()
    original = outcomes.copy(deep=True)
    result = prepare_v1_table(
        outcomes, geography_id="fixture-g1", source_version="fixture-outcomes",
        municipal_blocks=municipal, object_features=objects,
    )
    assert len(result.prepared) == 1
    assert len(result.candidate_columns) == 30
    row = result.prepared.iloc[0]
    assert row.population_total == 100
    assert row.target_share == .3
    assert row.policy_domain_01 == 1
    assert row.legal_form == "mandatory_referendum"
    assert pd.isna(row.history_vote_count)
    assert result.strict_population.empty
    assert result.readiness["status"] == "strict_population_empty"
    assert result.manifest["partitions"] is None
    assert result.manifest["final_test_used"] is False
    assert not {"yes_count", "no_count", "target_share", "vote_id"} & set(result.candidate_columns)
    pd.testing.assert_frame_equal(outcomes, original)
    repeated = prepare_v1_table(
        outcomes, geography_id="fixture-g1", source_version="fixture-outcomes",
        municipal_blocks=municipal, object_features=objects,
    )
    pd.testing.assert_frame_equal(result.prepared, repeated.prepared)
    assert result.manifest == repeated.manifest
    write_v1_artifacts(result, tmp_path / "first")
    write_v1_artifacts(repeated, tmp_path / "second")
    for first in (tmp_path / "first").iterdir():
        assert first.read_bytes() == (tmp_path / "second" / first.name).read_bytes()
    assert len(pd.read_parquet(tmp_path / "first" / "prepared.parquet")) == 1
    assert json.loads((tmp_path / "first" / "manifest.json").read_text())["final_test_used"] is False


def test_verified_sources_cannot_make_undeclared_history_ready():
    outcomes, objects, municipal = fixture_sources()
    for block in (*municipal, objects.feature_block):
        block.records["availability_status"] = "verified"
        block.records["published_at"] = "2018-01-01"
        block.records["reference_date"] = "2017-01-01"
        block.records["availability_evidence"] = "fixture documentary release"
    forecasts = pd.DataFrame([{
        "vote_id": "10", "forecast_at": "2018-02-01", "forecast_source": "fixture",
        "forecast_source_version": "fixture-v1", "forecast_evidence": "fixture brochure",
    }])
    result = prepare_v1_table(
        outcomes, geography_id="fixture-g1", source_version="fixture-outcomes",
        municipal_blocks=municipal, object_features=objects, forecast_publications=forecasts,
    )
    assert result.strict_population.empty
    assert result.exclusions.reason.eq("history_policy_not_configured").any()
    assert result.readiness["modeling_ready"] is False


def test_complete_verified_bundle_is_consumable_by_existing_evaluator(tmp_path):
    from scripts.modeling.evaluate_votes import EvaluationConfig, evaluate

    _, _, municipal = fixture_sources()
    dates = ("2010-03-01", "2012-03-01", "2013-03-01", "2014-03-01")
    outcomes = pd.DataFrame([{
        "municipality_id": "1", "vote_id": str(10 + number), "vote_date": date,
        "votes_yes": yes, "votes_no": 100 - yes, "is_special_unit": False,
        "is_tiebreak_question": False, "is_provisional": False,
    } for number, (date, yes) in enumerate(zip(dates, (20, 40, 60, 80)))])
    metadata = pd.DataFrame([{
        "anr": str((10 + number) / 10), "datum": date, "rechtsform": "1", "d1e1": "1", "d2e1": ".", "d3e1": ".",
    } for number, date in enumerate(dates)])
    objects = build_object_feature_block(
        outcomes, metadata, source_version="fixture-swissvotes", published_at="2009-01-01",
        reference_date="2009-01-01", publication_evidence="fixture documentary release",
    )
    municipal[0].records["published_at"] = "2009-01-01"
    municipal[0].records["reference_date"] = "2008-12-31"
    municipal[0].records["availability_status"] = "verified"
    municipal[0].records["availability_evidence"] = "fixture documentary release"
    forecasts = pd.DataFrame([{
        "vote_id": str(10 + number), "forecast_at": str(pd.Timestamp(date) - pd.Timedelta(days=30)),
        "forecast_source": "fixture", "forecast_source_version": "fixture-v1", "forecast_evidence": "fixture brochure",
    } for number, date in enumerate(dates)])
    publications = pd.DataFrame([{
        "vote_id": str(10 + number), "result_available_at": date, "result_source": "fixture",
        "result_source_version": "fixture-v1", "result_availability_evidence": "fixture results",
    } for number, date in enumerate(dates)])
    config = EvaluationConfig((dates[1],), (dates[2],), (dates[3],),
                              geography_mode="retrospective_fixed", ridge_alphas=(1.0,), bootstrap_replicates=2)
    result = prepare_v1_table(
        outcomes, geography_id="fixture-g1", source_version="fixture-outcomes",
        municipal_blocks=municipal, object_features=objects,
        forecast_publications=forecasts, result_publications=publications, history_config=config,
    )
    assert len(result.strict_population) == 3
    assert result.prepared.loc[result.prepared.vote_id.eq("11"), "history_yes_mean"].iloc[0] == .2
    assert result.manifest["partitions"]["train"] == ["2012-03-01"]
    evaluated = evaluate(
        result.strict_population, config, feature_blocks=result.feature_blocks,
        history_source=result.prepared, domain_records=result.domain_records,
    )
    assert len(evaluated["eligible_rows"]) == 3
    assert evaluated["predictions"].voting_date.eq(pd.Timestamp(dates[2], tz="UTC")).all()
    assert evaluated["joined_features"].loc[0, "history_yes_mean"] == .2
    assert evaluated["joined_features"].columns.is_unique
    models = set(evaluated["predictions"].model)
    assert {"ridge_v1_history", "ridge_history", "ridge_municipal", "ridge_swissvotes",
            "ridge_combined", "hist_gradient_boosting_history", "hist_gradient_boosting_combined"} <= models
    assert 'baseline_history_missing' in evaluated['manifest']['regularized']['ridge_history']['features']
    # Exported source blocks and Parquet domain arrays must also work through the
    # public CLI, rather than only with in-memory fixture DataFrames.
    import os
    import subprocess
    import sys
    from dataclasses import asdict

    write_v1_artifacts(result, tmp_path / 'bundle')
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps(asdict(config)))
    completed = subprocess.run([
        sys.executable, '-m', 'scripts.modeling.evaluate_votes',
        '--input', str(tmp_path / 'bundle/strict_population.parquet'),
        '--history-source', str(tmp_path / 'bundle/prepared.parquet'),
        '--domain-records', str(tmp_path / 'bundle/domain_records.parquet'),
        '--blocks', str(tmp_path / 'bundle/blocks.json'), '--config', str(config_path),
        '--output', str(tmp_path / 'evaluation'),
    ], capture_output=True, text=True, env={**os.environ, 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'})
    assert completed.returncode == 0, completed.stderr
    exported = pd.read_csv(tmp_path / 'evaluation/predictions.csv')
    assert set(exported.model) == models
    assert set(pd.to_datetime(exported.voting_date, utc=True)) == {pd.Timestamp(dates[2], tz='UTC')}


@pytest.mark.parametrize("include_valid", [True, False])
def test_invalid_object_keys_remain_auditable_through_complete_preparation(include_valid):
    outcomes, _, municipal = fixture_sources()
    invalid = outcomes.iloc[[0]].copy()
    invalid['vote_id'] = None
    malformed = outcomes.iloc[[0]].copy()
    malformed['vote_id'] = 'not-an-ofs-key'
    outcomes = pd.concat(([outcomes] if include_valid else []) + [invalid, malformed], ignore_index=True)
    metadata = pd.DataFrame([{"anr": '1.0', "datum": '04.03.2018', "rechtsform": '1',
                                   "d1e1": '1', "d2e1": '.', "d3e1": '.'}])
    objects = build_object_feature_block(outcomes, metadata, source_version='fixture-swissvotes')
    result = prepare_v1_table(outcomes, geography_id='fixture-g1', source_version='fixture-outcomes',
                              municipal_blocks=municipal, object_features=objects)
    assert len(result.prepared) == (3 if include_valid else 2)
    assert result.prepared.vote_id.isna().sum() == 2
    assert objects.join_audit.join_status.eq('invalid_ofs_identifier').sum() == 2
    assert result.exclusions.reason.eq('base_preparation_unresolved').sum() == 2
