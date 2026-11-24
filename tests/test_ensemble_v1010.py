import numpy as np
import pandas as pd

from scripts.modeling.ensemble_v1010 import gram, split_prediction, weights_from_history


def test_stack_simplex_and_strict_chronology():
    day=pd.Timestamp("2020-02-01")
    prior=np.array([.5,.5])
    hist=[{"date":pd.Timestamp("2020-01-01")+pd.Timedelta(days=i),
           "overall":gram(np.array([[.01,.2],[.01,.2]]))} for i in range(8)]
    a,n=weights_from_history(hist,day,prior,.1,"overall")
    b,m=weights_from_history(hist+[{"date":day,"overall":np.eye(2)*1000}],day,prior,.1,"overall")
    assert n==m==8
    assert a[0]>.5 and np.isclose(a.sum(),1) and (a>=0).all()
    np.testing.assert_array_equal(a,b)


def test_split_level_and_missing_history():
    x=np.array([[.1,.8],[.3,.9],[.4,1.]])
    w=np.array([1.,2.,3.])
    q=split_prediction(x,w,np.array([0.,1.]),np.array([1.,0.]))
    assert np.isclose(np.average(q,weights=w),np.average(x[:,1],weights=w))
    assert np.all((q>=0)&(q<=1))
    prior=np.array([.5,.5])
    p,n=weights_from_history([],pd.Timestamp("2020-01-01"),prior,.1,"overall")
    np.testing.assert_array_equal(p,prior)
    assert n==0
