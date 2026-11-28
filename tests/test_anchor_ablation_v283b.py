import numpy as np
import pandas as pd

from scripts.modeling.anchor_ablation_v283b import ablate


def test_structural_and_national_only():
    v = pd.DataFrame({"weight": [1., 1.], "poll_available": [True, True],
                      "language": ["other", "other"], "urban": ["other", "other"]})
    f = pd.DataFrame({"v8_reference": [.7, .7]})
    p = np.array([.2, .4])
    result = ablate(p, v, f, None, None)
    np.testing.assert_allclose(result["structural"], p)
    np.testing.assert_allclose(result["margins_only"], p)
    np.testing.assert_allclose(result["national_only"].mean(), .7, atol=1e-8)
    np.testing.assert_allclose(result["replay"], result["national_only"])


def test_no_poll_without_national():
    v = pd.DataFrame({"weight": [1., 2.], "poll_available": [False, False],
                      "language": ["other", "other"], "urban": ["other", "other"]})
    for q in ablate([-.1, 1.1], v, None, None, None).values():
        np.testing.assert_allclose(q, [0., 1.])


def test_margins_only_does_not_read_national(monkeypatch):
    calls = []

    def fake(p, v, f, lm, um):
        calls.append((bool(v.poll_available.iloc[0]), f, lm, um))
        return p

    monkeypatch.setattr("scripts.modeling.anchor_ablation_v283b.anchor", fake)
    v = pd.DataFrame({"poll_available": [True]})
    f, lm, um = object(), object(), object()
    ablate([.3], v, f, lm, um)
    assert calls == [(True, f, lm, um), (True, f, None, None), (False, None, lm, um)]
