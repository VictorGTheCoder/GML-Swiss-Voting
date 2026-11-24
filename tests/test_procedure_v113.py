import numpy as np
import pandas as pd

from scripts.modeling.procedure_v113 import procedural_features, select_extra


def example():
    return pd.DataFrame({"vote_key": ["1", "2", "3"],
                         "vote_date": pd.to_datetime(["2020-01-01"] * 3),
                         "dat-message": ["01.01.2018", "01.01.2018", "01.01.2018"],
                         "dat-parl": ["01.01.2019", "01.01.2020", "01.01.2019"],
                         "pa-iv": ["0", "0", "1"], "nrja": ["100", "100", "300"],
                         "nrnein": ["50", "50", "0"], "srja": ["20", "20", "20"],
                         "srnein": ["20", "20", "20"]})


def test_dates_and_special_cases():
    out = procedural_features(example())
    assert np.isclose(out.loc[0, "message_to_parliament_logdays"], np.log1p(365))
    assert out.loc[1, ["parliamentary_initiative", "parliament_to_vote_logdays",
                       "chamber_share_gap"]].isna().all()
    assert np.isnan(out.loc[2, "message_to_parliament_logdays"])
    assert np.isnan(out.loc[2, "nr_binary_seat_fraction"])


def test_chamber_disagreement():
    out = procedural_features(example())
    assert np.isclose(out.loc[0, "chamber_share_gap"], 2/3 - .5)
    assert np.isclose(out.loc[0, "nr_binary_seat_fraction"], .75)


def test_negative_correlation_pruned():
    train = pd.DataFrame({"a": -np.arange(20), "b": np.tile([0, 1], 10)})
    base = pd.DataFrame({"existing": np.arange(20)})
    keep, reasons = select_extra(train, base, ["a", "b"])
    assert keep == ["b"]
    assert reasons == {"a": "existing"}


def test_outcomes_not_used():
    a = example()
    b = a.assign(yes_share=[0., .5, 1.], **{"dat-force": "01.01.2021"})
    pd.testing.assert_frame_equal(procedural_features(a), procedural_features(b))
