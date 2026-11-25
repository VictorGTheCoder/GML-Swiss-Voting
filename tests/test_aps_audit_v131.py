from datetime import date

from scripts.modeling.aps_audit_v131 import audit, key_from_link


def test_swissvotes_link_exact():
    assert key_from_link("https://swissvotes.ch/vote/656.00") == "6560"
    assert key_from_link("https://swissvotes.ch/vote/656.1") == "6561"
    assert key_from_link("https://other.test/vote/656") is None
    assert key_from_link("https://swissvotes.ch/vote/656.01") is None


def test_cutoff_duplicates_and_missing_not_zero():
    header = "id.of.ad,publication.date,voting.date,link.to.swissvotes\n"
    row = "a,2022-05-04,2022-05-15,https://swissvotes.ch/vote/656\n"
    late = "b,2022-05-05,2022-05-15,https://swissvotes.ch/vote/656\n"
    mismatch = "c,2022-04-04,2022-05-14,https://swissvotes.ch/vote/656\n"
    outside = "d,2023-01-01,2023-01-15,https://swissvotes.ch/vote/656\n"
    result = audit((header + row + row + late + mismatch + outside).encode(),
                   {"6560": date(2022, 5, 15), "6570": date(2022, 5, 15)})
    assert result["matched_unique_records"] == 1
    assert result["missing_object_keys"] == ["6570"]
    assert result["diagnostics"] == {"duplicate_id_within_object": 1,
                                     "outside_j11_window": 1,
                                     "unmatched_development_rows": 1}
    assert result["training_rows_admitted"] == 0
