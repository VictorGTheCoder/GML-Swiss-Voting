from datetime import date

import pandas as pd
import pytest

from scripts.elections import build_election_features as module


def test_official_codes_disambiguate_identical_commune_names():
    raw = pd.DataFrame({
        "Place": ["......Same name"] * 4,
        "Year": ["2023"] * 4,
        "Party": ["A"] * 4,
        "Result": ["Votes", "Share"] * 2,
        "value": [10, 100, 20, 100],
        f"code_{module.GEO}": ["0001", "0001", "0002", "0002"],
        "code_Jahr": ["2023"] * 4,
        "code_Partei": ["1"] * 4,
        "code_Ergebnisse": ["1", "2"] * 2,
    })
    result = module.build(raw)
    assert result.municipality_id.tolist() == ["0001", "0002"]
    assert result.party_votes.tolist() == [10, 20]
    with pytest.raises(ValueError, match="Duplicate"):
        module.build(pd.concat([raw, raw.iloc[:1]], ignore_index=True))


def test_merge_recomputes_shares_from_counts_and_preserves_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "INTERIM_DIR", tmp_path)
    (tmp_path / "elections").mkdir()
    monkeypatch.setattr(module, "load_mutations", lambda: [(date(2025, 1, 1), 1, {"1": {"3"}, "2": {"3"}})])
    monkeypatch.setattr(module, "load_snapshot_codes", lambda day: {"3": "Merged"})
    table = pd.DataFrame({
        "municipality_id": ["0001", "0001", "0001", "0002", "0002", "0002"],
        "election_year": [2023] * 6, "party_code": ["1", "2", "3"] * 2,
        "party_name": ["A", "B", "C"] * 2,
        "party_votes": pd.array([20, 80, None, 900, 100, 0], dtype="Int64"),
        "municipality_name": ["First"] * 3 + ["Second"] * 3,
        "is_special_unit": [False] * 6,
    })
    result = module.harmonize(table).set_index("party_code")
    assert result.loc["1", "party_votes"] == 920
    assert result.loc["1", "party_share"] == pytest.approx(920 / 1100)
    assert pd.isna(result.loc["3", "party_votes"])
    assert result.loc["3", "source_values_missing"] == 1
    assert result.municipality_id.eq("0003").all()
    assert result.available_from.isna().all()
