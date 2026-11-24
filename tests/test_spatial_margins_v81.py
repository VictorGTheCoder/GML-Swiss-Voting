import numpy as np
import pandas as pd
import pytest

from scripts.modeling.spatial_margins_v81 import (
    checked_prediction,
    contrast_system,
    joint_adjust,
    latest_settlement,
    observation_system,
)


def test_joint_adjustment_respects_national_mean_and_improves_joint_contrasts():
    p = np.array([.3,.4,.5,.6,.7,.8])
    w = np.array([1.,2.,1.,3.,2.,1.])
    language = np.array(["de","de","fr","fr","it","it"])
    urban = np.array(["rural","medium","large","rural","medium","large"])
    a,z,b,i = observation_system(w,language,urban,np.array([.65,.48,.43]),np.array([.35,.53,.68]))
    q = joint_adjust(p,w,a,z,b,.1,False,i)
    checked_prediction(p,w,q)
    assert np.linalg.norm(a@q-z) < np.linalg.norm(a@p-z)


def test_contrast_is_translation_invariant():
    w = np.array([1.,2.,1.,4.])
    a,z,b = contrast_system(w,np.array(["a","b","b","c"]),("a","b","c"),np.array([.2,.3,.4]))
    assert np.allclose(a@np.ones(4),0)
    assert np.allclose(w@b,0)
    assert np.allclose(z,[.1,.2])


def test_missing_and_late_settlement():
    d = pd.DataFrame({"wave":[1]*3+[2]*3,"region":["rural","medium","large"]*2,
                      "published_at":["2022-01-01"]*3+["2022-02-01"]*3,
                      "yes_total":[30,40,50,60,70,80],"no_total":[70,60,50,40,30,20]})
    assert np.allclose(latest_settlement(d,"2022-01-15"),[.3,.4,.5])
    assert latest_settlement(d,"2021-12-31") is None
    assert latest_settlement(d.iloc[:0],"2022-03-01") is None


def test_empty_observations_and_invalid_weights():
    p = np.array([.2,.7])
    w = np.ones(2)
    a,z,b,i = observation_system(w,np.array(["de","fr"]),np.array(["rural","large"]),None,None)
    assert np.array_equal(joint_adjust(p,w,a,z,b,.1,False,i),p)
    with pytest.raises(ValueError):
        contrast_system(np.array([-1.,2.]),np.array(["a","b"]),("a","b"),np.array([.2,.4]))
