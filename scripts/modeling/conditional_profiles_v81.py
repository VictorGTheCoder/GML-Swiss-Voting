"""Stage 04: condition historical municipal contrast profiles on poll margins.

The V7 national-anchored forecast is the prior point estimate. The covariance
of low-rank residual coefficients is learned strictly before each outer fold.
Measurement noise is regularized; the empirical variant uses only previously
completed dates with all four contrasts observed. The two geographic margins
overlap and share respondents; no independent-binomial standard errors or
sample sizes are invented. This is a Gaussian conditioning experiment, not
individual-level inference or a calibrated probabilistic forecast.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.modeling.local_profiles_v7 import historical_matrix, metric_basis
from scripts.modeling.national_fusion_v81 import SPATIAL_BASES
from scripts.modeling.regional_anchor_v8 import LANGUAGES, gap_adjust, shift_to
from scripts.modeling.semantic_poll_comparison_v4 import sha
from scripts.modeling.spatial_margins_v81 import (
    checked_prediction,
    contexts,
    observation_system,
    score_row,
    summarize,
)
from scripts.modeling.temporal_drift_v6 import recency_weights

# Fixed grid declared before stage 04. Identical national bases to stage 03.
CONFIGS = {
    "latent5_noise4": (5,.04,.08,False,False),
    "latent10_noise4": (10,.04,.08,False,False),
    "latent20_noise4": (20,.04,.08,False,False),
    "latent10_noise8": (10,.08,.12,False,False),
    "latent20_noise8": (20,.08,.12,False,False),
    "latent10_empirical": (10,.04,.08,True,False),
    "latent20_empirical": (20,.04,.08,True,False),
    "latent10_language": (10,.04,.08,False,True),
}
FOLDS = (("2016-01-01","2018-12-31"),("2019-01-01","2020-12-31"),("2021-01-01","2022-12-31"))


def prior_noise(language_sd,urban_sd):
    block = np.array([[2.,1.],[1.,2.]])
    r = np.zeros((4,4))
    r[:2,:2] = block*language_sd**2
    r[2:,2:] = block*urban_sd**2
    return r


def measurement_noise(history,language_sd,urban_sd,empirical):
    """Shrunk second moment includes bias and cross-family correlations."""
    prior = prior_noise(language_sd,urban_sd)
    if not empirical or not history:
        return prior
    h = np.asarray(history,float)
    if h.ndim!=2 or h.shape[1]!=4 or not np.isfinite(h).all():
        raise ValueError("Expected four earlier poll contrast errors")
    return (h.T@h+8*prior)/(len(h)+8)


def center_basis(b,w):
    b = np.asarray(b,float).copy()
    b -= (w/w.sum())@b
    return b


def condition(p,w,b,cov,a,z,r):
    """Kalman-style low-rank conditional mean followed by national projection."""
    if not len(z):
        return p.copy()
    b = center_basis(b,w)
    h = a@b
    innovation_cov = h@cov@h.T+r
    if np.linalg.eigvalsh(innovation_cov).min()<=0:
        raise ValueError("Observation covariance must be positive definite")
    increment = cov@h.T@np.linalg.solve(innovation_cov,z-a@p)
    return checked_prediction(p,w,shift_to(p+b@increment,w,np.average(p,weights=w)))


def fit_prior(train,cutoff):
    if train.empty or train.vote_date.ge(cutoff).any():
        raise ValueError("Prior includes non-historical outcomes")
    meta = train[["vote_id","vote_date"]].drop_duplicates().sort_values(["vote_date","vote_id"])
    ids = meta.vote_id.tolist()
    munis,mu,residuals = historical_matrix(train,ids)
    w = recency_weights(meta.vote_date,cutoff,5)
    basis,heads = metric_basis(residuals,mu,w,np.ones(len(munis)),20,20261124)
    raw_cov = np.cov(heads[:,1:],rowvar=False,aweights=w)
    cov = .9*raw_cov+.1*np.diag(np.diag(raw_cov))+1e-9*np.eye(20)
    return pd.Index(munis),basis.components_.T,cov,len(ids)


def project_basis(prior,munis,rank):
    index,b,cov,_ = prior
    pos = index.get_indexer(munis)
    result = np.zeros((len(pos),rank))
    result[pos>=0] = b[pos[pos>=0],:rank]
    return result,cov[:rank,:rank]


def run(base,acquisition,fusion,spatial,output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve previous run")
    sm = json.loads((spatial/"manifest.json").read_text())
    if sm["status"]!="complete" or sm["national_prediction_hash"]!=sha(fusion/"national_predictions.parquet"):
        raise ValueError("Stage 03 must pass with identical national predictions")
    data,cases = contexts(base,acquisition,fusion)
    priors = {start:fit_prior(data[data.vote_date.lt(start)],start) for start,_ in FOLDS}
    errors,records,audit = [],[],[]
    previous_day = None
    pending = []
    for vote,day,v,f,lm,um in cases:
        if previous_day is not None and day!=previous_day:
            if day<previous_day:
                raise ValueError("Dates must increase")
            errors.extend(pending)
            pending = []
        previous_day = day
        start = next(s for s,e in FOLDS if pd.Timestamp(s)<=day<=pd.Timestamp(e))
        prior = priors[start]
        w,y = v.weight.to_numpy(float),v.yes_share.to_numpy(float)
        language,urban = v.language.to_numpy(),v.urban.to_numpy()
        full_a,full_z,_,full_indices = observation_system(w,language,urban,lm,um)
        for name in SPATIAL_BASES:
            p = f[name].to_numpy(float)
            ref = gap_adjust(p,w,language,LANGUAGES,lm,1.) if lm is not None else p
            records.append(score_row(vote,day,name,"language",y,ref,lm,um))
            for method,(rank,lsd,usd,empirical,language_only) in CONFIGS.items():
                a,z,indices = full_a,full_z,full_indices
                if language_only:
                    take = indices<2
                    a,z,indices = a[take],z[take],indices[take]
                b,cov = project_basis(prior,v.municipality_id.to_numpy(),rank)
                r = measurement_noise(errors,lsd,usd,empirical)[np.ix_(indices,indices)]
                result = condition(p,w,b,cov,a,z,r)
                records.append(score_row(vote,day,name,method,y,result,lm,um))
        audit.append({"vote_id":vote,"vote_date":str(day.date()),"prior_cutoff":start,
                      "prior_objects":prior[3],"earlier_complete_poll_error_vectors":len(errors),
                      "observations":len(full_indices)})
        if len(full_indices)==4:
            pending.append(full_z-full_a@y)
    ref = "v8_reference__language"
    d,s = summarize(records,ref)
    if not np.isclose(next(r["mae"] for r in s if r["variant"]==ref),7.340163035010155,atol=.0002,rtol=0):
        raise ValueError("V8 reference not reproduced")
    output.mkdir(parents=True,exist_ok=True)
    d.to_csv(output/"object_metrics.csv",index=False)
    pd.DataFrame(s).to_csv(output/"summary.csv",index=False)
    pd.DataFrame(audit).to_csv(output/"chronology_audit.csv",index=False)
    (output/"manifest.json").write_text(json.dumps({"status":"complete","strict_forecast_ready":False,
        "prior":"five-year recency-weighted historical municipal contrasts, strictly before each fold",
        "same_date_excluded":True,"spatial_manifest_sha256":sha(spatial/"manifest.json"),
        "summary":s},indent=2,allow_nan=False),encoding="utf-8")
    print("SUMMARY",json.dumps(s,allow_nan=False),flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("base","acquisition","fusion","spatial","output"):
        p.add_argument("--"+n,type=Path,required=True)
    a = p.parse_args()
    run(a.base,a.acquisition,a.fusion,a.spatial,a.output)


if __name__=="__main__":
    main()
