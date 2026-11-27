import numpy as np
import pandas as pd
import pytest

from scripts.modeling.session_v211 import COUNT, PEERS, peer_context


def example():
    return pd.DataFrame({"vote_key": ["1", "2", "3"],
                         "vote_date": pd.to_datetime(["2020-01-01"] * 3),
                         "dat-message": ["01.01.2018"] * 3,
                         "dat-parl": ["01.01.2019", "01.01.2020", "01.01.2019"],
                         "pa-iv": ["0", "0", "1"], "nrja": ["100", "100", "300"],
                         "nrnein": ["50", "50", "0"], "srja": ["20", "20", "20"],
                         "srnein": ["20", "20", "20"]})


def test_leave_focal_out_and_missing():
    raw = example()
    result = peer_context(raw)
    assert result[COUNT[0]].tolist() == [2, 2, 2]
    assert np.isclose(result.loc[0, PEERS[0]], 1.)
    assert np.isclose(result.loc[2, PEERS[0]], 0.)
    assert np.isnan(result.loc[0, "session_peer_nr_binary_seat_fraction"])
    assert np.isclose(result.loc[2, "session_peer_nr_binary_seat_fraction"], .75)


def test_singleton_and_date_isolation():
    raw = example()
    raw.loc[2, "vote_date"] = pd.Timestamp("2020-02-01")
    a = peer_context(raw)
    assert a.loc[2, COUNT[0]] == 0
    assert a.loc[2, PEERS].isna().all()
    raw.loc[2, "pa-iv"] = "0"
    pd.testing.assert_frame_equal(a.iloc[:2], peer_context(raw).iloc[:2])


def test_target_columns_ignored():
    raw = example()
    pd.testing.assert_frame_equal(peer_context(raw), peer_context(raw.assign(yes_share=[0., .5, 1.])))


def test_fail_closed():
    raw = example()
    with pytest.raises(ValueError):
        peer_context(pd.concat([raw, raw], ignore_index=True))
    raw.loc[2, "vote_date"] = pd.Timestamp("2023-01-01")
    with pytest.raises(ValueError):
        peer_context(raw)
