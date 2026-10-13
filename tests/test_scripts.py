"""Regression tests for the PX pipeline and Swissvotes download (offline)."""

import importlib
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from scripts import run_pipeline
from scripts import votes_config as config
from scripts.cleaning import (
    audit_ofs_votes,
    clean_ofs_votes,
    parse_ofs_votes,
    validate_ofs_votes,
)
from scripts.download import download_ofs_votes, download_swissvotes


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Unexpected network request")
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(requests, "post", blocked)


def test_imports_have_no_side_effects():
    for module in (download_ofs_votes, download_swissvotes, run_pipeline):
        importlib.reload(module)


def test_paths_are_under_project_data():
    for path in (config.RAW_PX_PATH, config.SWISSVOTES_PATH, config.PROCESSED_PATH):
        assert path.is_relative_to(config.ROOT / "data")
    assert config.ROOT == Path(__file__).resolve().parents[1]


def test_cached_swissvotes_never_contacts_network(tmp_path):
    output = tmp_path / "cached.csv"
    output.write_text("cached", encoding="utf-8")
    assert download_swissvotes.download_swissvotes(output=output) == output
    assert output.read_text() == "cached"


def test_download_creates_parent_and_provenance(tmp_path, monkeypatch):
    output = tmp_path / "new" / "swissvotes.csv"
    response = Mock(content=b"anr;datum\n001;12.09.1848\n")
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    download_swissvotes.download_swissvotes(output=output, force=True)
    assert output.read_bytes() == response.content
    assert output.with_suffix(".provenance.json").exists()
    response.raise_for_status.assert_called_once()


def test_invalid_download_preserves_existing_file(tmp_path, monkeypatch):
    output = tmp_path / "source.csv"
    output.write_bytes(b"original")
    response = Mock(content=b"<html>Server error</html>\n")
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    with pytest.raises(ValueError):
        download_swissvotes.download_swissvotes(force=True, output=output)
    assert output.read_bytes() == b"original"
    assert not output.with_suffix(".csv.part").exists()


@pytest.fixture
def raw_frame():
    return pd.DataFrame([{
        "level": "commune", "vote_id": "1", "location_code": "0001",
        "location_name_fr": "Commune", "location_name_de": "Gemeinde",
        "vote_label_fr": "2024-01-01 Objet", "vote_label_de": "2024-01-01 Vorlage",
        "canton": "ZH", "district_code": None, "district_name": None,
        "eligible_voters": 100., "ballots_cast": 80., "valid_ballots": 80.,
        "votes_yes": 60., "votes_no": 20., "yes_pct_ofs": 75., "turnout_pct_ofs": 80.,
    }])


def test_cleaning_and_validation_roundtrip(raw_frame, tmp_path):
    clean, _ = clean_ofs_votes.clean_votes(raw_frame)
    assert clean.loc[0, "yes_share"] == 0.75
    assert clean.loc[0, "municipality_id"] == "0001"
    validate_ofs_votes.assert_valid(validate_ofs_votes.run_checks(clean))
    path = tmp_path / "votes.parquet"
    clean.to_parquet(path, index=False)
    pd.testing.assert_frame_equal(clean, pd.read_parquet(path))


def test_empty_clean_dataset_is_rejected(raw_frame):
    raw_frame["votes_yes"] = 0.
    raw_frame["votes_no"] = 0.
    clean, _ = clean_ofs_votes.clean_votes(raw_frame)
    with pytest.raises(validate_ofs_votes.ValidationError, match="non_empty"):
        validate_ofs_votes.assert_valid(validate_ofs_votes.run_checks(clean))


def test_fractional_counts_are_rejected(raw_frame):
    raw_frame["votes_yes"] = 60.5
    clean, _ = clean_ofs_votes.clean_votes(raw_frame)
    with pytest.raises(validate_ofs_votes.ValidationError, match="integer:votes_yes"):
        validate_ofs_votes.assert_valid(validate_ofs_votes.run_checks(clean))


def test_audit_does_not_count_missing_as_fractional(raw_frame, monkeypatch):
    raw_frame["eligible_voters"] = float("nan")
    tables = []
    monkeypatch.setattr(audit_ofs_votes, "_md", lambda frame: tables.append(frame) or "table")
    audit_ofs_votes.section_consistency(audit_ofs_votes._with_dates(raw_frame))
    checks = tables[0].set_index("check")
    assert checks.loc["non-integer counts", "value"] == 0


def test_px_metadata_requires_data_section(tmp_path):
    path = tmp_path / "invalid.px"
    path.write_text('MATRIX="wrong";\n', encoding="utf-8")
    with pytest.raises(ValueError, match="no DATA"):
        parse_ofs_votes.read_px_metadata(path)


def test_hierarchy_rejects_mismatched_labels():
    with pytest.raises(ValueError):
        parse_ofs_votes.location_hierarchy(["CH", "ZH"], ["Schweiz"], ["Suisse"])


def test_wrong_px_cube_preserves_existing_file(tmp_path, monkeypatch):
    output = tmp_path / "cube.px"
    output.write_bytes(b"original")
    response = Mock()
    response.iter_content.return_value = [b'AXIS-VERSION="2013";\nMATRIX="wrong";\nDATA=1;']
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(requests, "get", Mock(return_value=context))
    with pytest.raises(RuntimeError, match="expected"):
        download_ofs_votes.download("https://example.test/cube", output)
    assert output.read_bytes() == b"original"
    assert not output.with_suffix(".px.part").exists()


@pytest.fixture
def px_cube():
    meta = {
        "STUB": [config.DIM_LOCATION, config.DIM_VOTE],
        "HEADING": [config.DIM_RESULT],
        f'CODES("{config.DIM_LOCATION}")': ["CH", "ZH", "0001"],
        f'VALUES("{config.DIM_LOCATION}")': ["Schweiz", "- Zürich", "......Gemeinde"],
        f'VALUES[fr]("{config.DIM_LOCATION_FR}")': ["Suisse", "- Zurich", "......Commune"],
        f'CODES("{config.DIM_VOTE}")': ["10"],
        f'VALUES("{config.DIM_VOTE}")': ["2024-01-01 Vorlage"],
        f'VALUES[fr]("{config.DIM_VOTE_FR}")': ["2024-01-01 Objet"],
        f'CODES("{config.DIM_RESULT}")': list(config.RESULT_COLUMNS),
        f'VALUES("{config.DIM_RESULT}")': list(config.RESULT_COLUMNS.values()),
        'VALUES[fr]("Résultat")': list(config.RESULT_COLUMNS.values()),
        "MATRIX": [config.OFS_TABLE_ID],
    }
    tokens = ['"..."'] * 14 + ["100", "80", "80", "80", "60", "20", "75"]
    return parse_ofs_votes.PxFile(meta, tokens)


def test_px_cube_order_and_missing_values(px_cube):
    frame = parse_ofs_votes.px_to_long(px_cube)
    assert frame["level"].tolist() == ["country", "canton", "commune"]
    assert pd.isna(frame.loc[0, "votes_yes"])
    assert frame.loc[2, "votes_yes"] == 60
    assert frame.attrs["missing_symbols"] == {'"..."': 14}
    clean, _ = clean_ofs_votes.clean_votes(frame)
    validate_ofs_votes.assert_valid(validate_ofs_votes.run_checks(clean))
    assert len(clean) == 1


def test_markdown_reports(raw_frame):
    clean, log = clean_ofs_votes.clean_votes(raw_frame)
    assert "keep_commune_level" in log.to_markdown()
    report = validate_ofs_votes.checks_to_markdown(validate_ofs_votes.run_checks(clean), len(clean))
    assert "PASS" in report
    assert "FAIL" not in report
    assert "non-integer counts" in audit_ofs_votes.section_consistency(audit_ofs_votes._with_dates(raw_frame))


def test_cached_px_never_contacts_network(tmp_path, monkeypatch):
    path = tmp_path / "cube.px"
    path.write_text("cached", encoding="utf-8")
    monkeypatch.setattr(download_ofs_votes, "RAW_PX_PATH", path)
    monkeypatch.setattr(download_ofs_votes, "PROVENANCE_PATH", tmp_path / "cube.provenance.json")
    assert download_ofs_votes.ensure_raw_data() == path
    assert path.read_text() == "cached"


@pytest.mark.parametrize("invalid", [False, True])
def test_pipeline_px_to_validated_parquet(tmp_path, monkeypatch, px_cube, invalid):
    # Execute every processing stage on a small local PX cube; only HTTP is mocked.
    from scripts import prepare_join, run_pipeline
    from scripts.cleaning import clean_swissvotes

    if invalid:
        px_cube.data_tokens[-1] = "10"  # Published percentage disagrees with yes/no counts.
    px_path = tmp_path / "cube.px"
    header = "\n".join(
        key + "=" + ",".join('"' + value + '"' for value in values) + ";"
        for key, values in px_cube.metadata.items()
    )
    px_path.write_text(header + "\nDATA=" + " ".join(px_cube.data_tokens) + ";", encoding="utf-8")
    paths = {
        "RAW_PX_PATH": px_path,
        "PROVENANCE_PATH": tmp_path / "cube.provenance.json",
        "INTERIM_PATH": tmp_path / "interim" / "all.parquet",
        "CLEAN_PATH": tmp_path / "interim" / "clean.parquet",
        "PROCESSED_PATH": tmp_path / "processed" / "votes.parquet",
        "AUDIT_PATH": tmp_path / "reports" / "audit.md",
        "CLEANING_LOG_PATH": tmp_path / "reports" / "cleaning.md",
        "VALIDATION_REPORT_PATH": tmp_path / "reports" / "validation.md",
        "SWISSVOTES_PATH": tmp_path / "swissvotes.csv",
        "SWISSVOTES_CLEAN_PATH": tmp_path / "processed" / "swissvotes.parquet",
        "SWISSVOTES_REPORT_PATH": tmp_path / "reports" / "swissvotes.md",
        "JOIN_REPORT_PATH": tmp_path / "reports" / "join.md",
        "VOTE_CROSSWALK_PATH": tmp_path / "processed" / "crosswalk.parquet",
    }
    paths["SWISSVOTES_PATH"].write_text(
        "anr;datum;titel_kurz_d;titel_kurz_f;rechtsform\n1;01.01.2024;Vorlage;Objet;1\n", encoding="utf-8"
    )
    for module in (config, parse_ofs_votes, audit_ofs_votes, clean_ofs_votes, validate_ofs_votes, clean_swissvotes, prepare_join):
        for name, path in paths.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, path)
    ofs_download = Mock(return_value=px_path)
    swiss_download = Mock()
    monkeypatch.setattr(download_ofs_votes, "ensure_raw_data", ofs_download)
    monkeypatch.setattr(download_swissvotes, "download_swissvotes", swiss_download)

    if invalid:
        with pytest.raises(validate_ofs_votes.ValidationError):
            run_pipeline.run_pipeline(force=True)
        assert not paths["PROCESSED_PATH"].exists()
    else:
        run_pipeline.run_pipeline(force=True)
        result = pd.read_parquet(paths["PROCESSED_PATH"])
        assert len(result) == 1
        assert result.loc[0, "municipality_id"] == "0001"
        assert result.loc[0, "yes_share"] == 0.75
        crosswalk = pd.read_parquet(paths["VOTE_CROSSWALK_PATH"])
        assert crosswalk["join_status"].tolist() == ["matched"]
        assert paths["SWISSVOTES_CLEAN_PATH"].is_file()
    ofs_download.assert_called_once_with(force=True)
    swiss_download.assert_called_once_with(force=True)
    for name in ("INTERIM_PATH", "CLEAN_PATH", "AUDIT_PATH", "CLEANING_LOG_PATH", "VALIDATION_REPORT_PATH"):
        assert paths[name].is_file()
