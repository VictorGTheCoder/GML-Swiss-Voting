import numpy as np
import pandas as pd
import pytest

from scripts.modeling.conditional_profiles_v81 import condition, fit_prior, measurement_noise, prior_noise


def test_condition_preserves_level_and_reduces_innovation():
    p = np.array([.4,.5,.6,.5])
    w = np.array([1.,2.,2.,1.])
    b = np.array([[1.],[1.],[-1.],[-1.]])
    a = np.array([[.5,.5,-.5,-.5]])
    z = np.array([.25])
    q = condition(p,w,b,np.array([[.03]]),a,z,np.array([[.002]]))
    assert np.isclose(w@p,w@q)
    assert np.abs(a@q-z)<np.abs(a@p-z)
    assert np.all((q>=0)&(q<=1))


def test_missing_poll_returns_identical_forecast():
    p = np.array([.4,.5])
    q = condition(p,np.ones(2),np.ones((2,1)),np.eye(1),np.empty((0,2)),np.empty(0),np.empty((0,0)))
    assert np.array_equal(p,q)


def test_empirical_noise_is_positive_definite_and_preserves_cross_correlations():
    h = [[.04,.04,.08,.08],[-.04,-.04,-.08,-.08]]
    r = measurement_noise(h,.04,.08,True)
    assert np.linalg.eigvalsh(r).min()>0
    assert r[0,2]>0
    assert np.array_equal(measurement_noise([], .04,.08,True),prior_noise(.04,.08))
    assert np.array_equal(measurement_noise(h,.04,.08,False),prior_noise(.04,.08))


def test_fit_prior_rejects_same_date():
    with pytest.raises(ValueError,match="non-historical"):
        fit_prior(pd.DataFrame({"vote_date":pd.to_datetime(["2021-01-01"])}),"2021-01-01")
