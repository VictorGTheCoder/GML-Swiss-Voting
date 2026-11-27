from scripts.modeling.stability_v251 import METRICS, NAMES, bootstrap, compare, read_panel

import pytest


def test_macro_objects_not_equal_dates():
    keys = [("2016-01-01", "a"), ("2016-01-01", "b"), ("2016-02-01", "c")]
    panel = {n: {k: dict.fromkeys(METRICS, 10.0) for k in keys} for n in NAMES}
    for k in keys[:2]:
        panel["scaled_squared"][k]["mae_pp"] = 7.0
    assert compare(panel, keys, [])["gain_scaled_vs_v113"] == 2.0
    assert compare(panel, keys, [keys[0][0]])["gain_scaled_vs_v113"] == 0.0
    assert bootstrap(panel, keys, "v113_institution", "scaled_squared", reps=100) == [0.0, 3.0]


def test_reject_forbidden_date(tmp_path):
    path = tmp_path / "metrics.csv"
    path.write_text("variant,vote_date,vote_id,mae_pp\nreference,2023-01-01,a,1\n")
    with pytest.raises(ValueError, match="Forbidden date"):
        read_panel(path)
