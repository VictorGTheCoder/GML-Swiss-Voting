"""Check that the design audit uses only training object attributes."""

import numpy as np
import pandas as pd
import pytest

from scripts.modeling.encoded_redundancy_v3 import fit_object_design, read_object_units
from scripts.modeling.feature_redundancy_v3 import audit_scope


def frame():
    x = np.tile([0., 1.], 15)
    return pd.DataFrame({"municipality_id": ["a"] * 30, "vote_id": [str(i) for i in range(30)],
                         "vote_date": pd.to_datetime(["2015-01-01"] * 30),
                         "sign": 2 * x - 1, "recommendation": np.where(x, "yes", "no")})


def test_actual_preprocessor_exposes_numeric_onehot_redundancy_without_targets():
    source = frame()
    design, _ = fit_object_design(source, ["sign"], ["recommendation"])
    changed, _ = fit_object_design(source.assign(yes_share=np.arange(30) / 30), ["sign"], ["recommendation"])
    pd.testing.assert_frame_equal(design, changed)
    assert len(design) == 30
    _, pairs = audit_scope(design, list(design), [])
    assert any(row["feature_a"] == "numeric__sign" and row["hard_redundancy_candidate"] for row in pairs)


def test_unknown_categories_can_break_training_dummy_complementarity():
    source = frame()
    design, preprocessor = fit_object_design(source, ["sign"], ["recommendation"])
    yes, no = "categorical__recommendation_yes", "categorical__recommendation_no"
    np.testing.assert_array_equal(design[yes] + design[no], np.ones(len(design)))
    future = pd.DataFrame({"sign": [0.], "recommendation": ["free_vote"]})
    encoded = pd.DataFrame(preprocessor.transform(future), columns=preprocessor.get_feature_names_out())
    assert float(encoded[yes].iloc[0] + encoded[no].iloc[0]) == 0


def test_streaming_object_reader_excludes_future_rows_and_detects_conflicts(tmp_path):
    source = frame()
    repeated = pd.concat([source, source.assign(municipality_id="b")], ignore_index=True)
    future = pd.DataFrame({"municipality_id": ["a"], "vote_id": ["future"],
                           "vote_date": pd.to_datetime(["2023-01-01"]), "sign": [100.],
                           "recommendation": ["unseen"]})
    path = tmp_path / "features.parquet"
    pd.concat([repeated, future], ignore_index=True).to_parquet(path, index=False)
    units = read_object_units(path, ["sign"], ["recommendation"], start="1990-01-01", end="2016-01-01")
    assert len(units) == 30 and "future" not in units.vote_id.tolist()
    repeated.loc[len(source), "sign"] = 0
    repeated.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="disagree"):
        read_object_units(path, ["sign"], ["recommendation"], start="1990-01-01", end="2016-01-01")
