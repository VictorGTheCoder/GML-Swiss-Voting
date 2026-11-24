"""V9 invariant tests for features and complementary panels."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling.remaining_priorities_v9 import (
    centered_design,
    economic_lookup,
    panel_indices,
    reconstruct_panel,
    text_features,
)


def test_economic_join_never_uses_later_year():
    data=pd.DataFrame({"vote_id":["v"],"municipality_id":["0001"],"vote_date":pd.to_datetime(["2016-02-01"]),
                       "statpop_pop_total":[100.],"statpop_share_foreign":[.1],"statpop_share_0_19":[.2]})
    econ=pd.DataFrame({"municipality_id":["0001","0001"],"year":[2014,2015],
                       "available_from_proxy":pd.to_datetime(["2016-01-01","2017-01-01"]),
                       "econ_share_primary":[.1,.9],"econ_share_secondary":[.2,.2],
                       "econ_share_tertiary":[.7,.1],"econ_log_jobs":[2.,3.],"econ_log_establishments":[1.,2.]})
    assert economic_lookup(data,econ).econ_share_primary.iloc[0]==.1
    econ.loc[0,"available_from_proxy"]=pd.Timestamp("2016-03-01")
    with pytest.raises(ValueError):
        economic_lookup(data,econ)


def test_centered_design_keeps_missingness_explicit():
    x,valid=centered_design(np.array([[.1,np.nan],[.2,1.],[.3,2.]]))
    assert not valid[0,1]
    assert x[0,1]==0.
    np.testing.assert_allclose(x.mean(axis=0),0,atol=1e-10)


def test_panel_selection_unique_and_can_reconstruct_without_labels():
    rng=np.random.default_rng(1)
    b,_=np.linalg.qr(rng.normal(size=(50,5)))
    eligible=np.ones(50,bool)
    eligible[0]=False
    k=panel_indices(b,eligible,10)
    assert len(set(k))==10 and 0 not in k
    c=np.array([.1,-.2,.3,-.1,.2])
    center=rng.normal(size=50)*.02
    synthetic=.5+center+b@c
    level,coef=reconstruct_panel(synthetic[k],b[k],center[k],b,penalty=0.)
    assert level==pytest.approx(.5)
    np.testing.assert_allclose(coef,c,atol=1e-10)


def test_text_transform_is_independent_of_other_query():
    corpus=pd.DataFrame({"title_text":["loi sur les impots","loi sur le revenu","loi sur les routes","impot national","impot communal","loi sur la mer"],
                         "document_text":["loi sur les impots","loi sur le revenu","loi sur les routes","impot national","impot communal","loi sur la mer"],
                         "usable_summary":[False]*6},index=list("abcdef"))
    a,b=text_features(corpus,list("abcd"),["e"],"tfidf_title",2)
    c,d=text_features(corpus,list("abcd"),["e","f"],"tfidf_title",2)
    np.testing.assert_allclose(a,c)
    np.testing.assert_allclose(b,d[:1])
