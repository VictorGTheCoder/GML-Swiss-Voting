"""Acquisition gate tests: no order-based matching, no ambiguous margins."""
from scripts.modeling.collect_poll_features import FIELDS
from scripts.modeling.poll_acquisition_v81 import extract_settlement, settlement_label


def test_exact_settlement_labels():
    assert settlement_label("kleine/mittlere\n  Agglomeration 18. März 2022") == "medium"
    assert settlement_label("grosse Agglomeration") == "large"
    assert settlement_label("ländlich") == "rural"
    assert settlement_label("unbekannt") is None


def test_settlement_rows_no_guessing_and_dates():
    header = [None, "bestimmt dafür", "eher dafür", "weiss nicht/keine Antwort", "eher dagegen", "bestimmt dagegen"]
    sheet = [header, ["ländlich 1. Mai 2022", 30, 20, 5, 15, 30],
             ["kleine/mittlere Agglomeration 1. Mai 2022", 40, 20, 5, 15, 20],
             ["grosse Agglomeration 1. Mai 2022", 50, 10, 5, 15, 20]]
    result = extract_settlement([("/data/0", sheet)], "2022-05-01", 2)
    assert len(result) == 3
    assert set(FIELDS).issubset(result[0])
    assert extract_settlement([("/data/0", sheet)], "2022-05-02", 2) == []
    conflict = sheet + [["ländlich 1. Mai 2022", 10, 20, 5, 15, 50]]
    assert extract_settlement([("/data/0", conflict)], "2022-05-01", 2) == []
