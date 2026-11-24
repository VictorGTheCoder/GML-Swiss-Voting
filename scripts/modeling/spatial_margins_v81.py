"""Stage 03: jointly reconcile overlapping poll margins.

The settlement classification is explicitly an unverified OFS proxy, NOT
an exact crosswalk to gfs.bern's agglomeration-size categories. All adjustment
operators use only known weights, the frozen national predictions and polls.
No current vote outcome enters a prediction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.audit_xgboost_capacity import diagnostics
from scripts.modeling.national_fusion_v81 import SPATIAL_BASES
from scripts.modeling.poll_acquisition_v81 import URBAN_LABELS
from scripts.modeling.regional_anchor_v8 import (
    LANGUAGES,
    REGIONS,
    gap_adjust,
    load_regional,
    regional_target,
    shift_to,
)
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.semantic_training_v5 import (
    CURRENT_POLLS,
    EXTRAS,
    HISTORICAL,
    HISTORICAL_POLLS,
    PLAN,
    V4,
    prepare_data,
)

VARIANTS = ("national", "language", "urban25", "urban50", "urban100",
            "joint_ridge10", "joint_ridge30", "joint_urban_weaker")
CROSSWALK = {"1": "large", "2": "medium", "3": "rural"}


def load_settlement(path, national):
    """Validate raw settlement cells against reviewed chart identity."""
    d = pd.read_csv(path, dtype={"vote_key": str})
    fields = ["yes_certain", "yes_lean", "undecided", "no_lean", "no_certain"]
    if d.duplicated(["vote_key", "wave", "region"]).any():
        raise ValueError("Duplicate settlement observation")
    if not d.region.isin(URBAN_LABELS).all():
        raise ValueError("Unknown settlement label")
    if not d.groupby(["vote_key", "wave"]).region.nunique().eq(3).all():
        raise ValueError("Incomplete settlement wave")
    if not d[fields].apply(lambda s: s.between(0, 100).all()).all():
        raise ValueError("Invalid settlement proportions")
    if (d[fields].sum(axis=1)-100).abs().gt(2.01).any():
        raise ValueError("Rounding tolerance exceeded")
    if not np.allclose(d.yes_total, d.yes_certain+d.yes_lean) or not np.allclose(d.no_total,d.no_lean+d.no_certain):
        raise ValueError("Inconsistent response totals")
    if not d.historical_version_verified.astype(str).str.lower().eq("false").all():
        raise ValueError("Historical versions not independently verified")
    keys = ["vote_key", "wave"]
    meta = ["vote_date", "survey_midpoint", "published_at", "chart_url"]
    j = d.merge(national[keys+meta], on=keys, how="left", validate="many_to_one", suffixes=("", "_n"))
    if any(not j[c].eq(j[c+"_n"]).all() for c in meta):
        raise ValueError("Settlement source/wave mismatch")
    pub = pd.to_datetime(d.published_at, utc=True)
    vote = pd.to_datetime(d.vote_date, utc=True)
    if not pub.le(vote-pd.Timedelta(days=1)).all():
        raise ValueError("Settlement poll unavailable at cutoff")
    return d


def latest_settlement(rows, day):
    if rows.empty:
        return None
    cutoff = pd.Timestamp(day, tz="UTC")-pd.Timedelta(days=1)
    eligible = rows[pd.to_datetime(rows.published_at, utc=True).le(cutoff)]
    if eligible.empty:
        return None
    a = eligible[eligible.wave.eq(eligible.wave.max())].set_index("region").reindex(URBAN_LABELS)
    y, n = a.yes_total.to_numpy(float), a.no_total.to_numpy(float)
    if not np.isfinite(y+n).all() or (y+n <= 0).any():
        return None
    return y/(y+n)


def contrast_system(w, groups, labels, margins):
    """Return independent contrasts against first group and group indicators."""
    w = np.asarray(w, float)
    groups = np.asarray(groups)
    if (w < 0).any() or not np.isfinite(w).all() or w.sum() <= 0:
        raise ValueError("Bad municipal weights")
    if margins is None:
        return None
    z = np.asarray(margins, float)
    if z.shape != (len(labels),) or not np.isfinite(z).all() or (z<0).any() or (z>1).any():
        raise ValueError("Bad survey margins")
    b = np.column_stack([groups == k for k in labels]).astype(float)
    masses = b.T@w
    if (masses<=0).any():
        raise ValueError("A surveyed group has no municipal population proxy")
    means = b.T*w[None,:]/masses[:,None]
    a = means[1:]-means[:1]
    # Center the indicator space with the nationwide population proxy.
    b -= (w/w.sum())@b
    return a,z[1:]-z[0],b


def observation_system(w, language, urban, lm, um):
    systems = [contrast_system(w,language,LANGUAGES,lm),
               contrast_system(w,urban,URBAN_LABELS,um)]
    present = [s for s in systems if s is not None]
    indices = np.concatenate([np.arange(2)+2*i for i,s in enumerate(systems) if s is not None]) if present else np.array([],int)
    if not present:
        return np.empty((0,len(w))),np.empty(0),np.empty((len(w),0)),indices
    return np.vstack([s[0] for s in present]),np.concatenate([s[1] for s in present]),np.column_stack([s[2] for s in present]),indices


def joint_adjust(p,w,a,z,b,ridge,urban_weaker=False,indices=None):
    """Solve a coupled ridge problem instead of sequentially overwriting margins."""
    if not len(z):
        return p.copy()
    h = a@b
    # Contrast pairs share a reference category. Their errors are correlated.
    block = np.array([[2.,1.],[1.,2.]])
    covariance = np.zeros((4,4))
    covariance[:2,:2] = block
    covariance[2:,2:] = block*(4. if urban_weaker else 1.)
    precision = np.linalg.inv(covariance[np.ix_(indices,indices)])
    coefficients = np.linalg.solve(h.T@precision@h+ridge*np.eye(b.shape[1]),h.T@precision@(z-a@p))
    result = shift_to(p+b@coefficients,w,np.average(p,weights=w))
    return result


def checked_prediction(p,w,result):
    if not np.isfinite(result).all() or (result<0).any() or (result>1).any():
        raise ValueError("Invalid probability")
    if abs(np.average(result-p,weights=w))>1e-8:
        raise ValueError("Spatial correction changed national anchor")
    return result


def contexts(base, acquisition, fusion):
    acq = json.loads((acquisition/"manifest.json").read_text())
    if sha(acquisition/"settlement_polls.csv") != acq["hashes"]["settlement_polls.csv"]:
        raise ValueError("Acquisition changed")
    fm = json.loads((fusion/"manifest.json").read_text())
    if fm["status"]!="complete" or fm["prediction_hash"]!=sha(fusion/"national_predictions.parquet"):
        raise ValueError("National fusion gate failed")
    pred = pd.read_parquet(fusion/"national_predictions.parquet")
    pred["municipality_id"],pred["vote_id"] = pred.municipality_id.astype(str),pred.vote_id.astype(str)
    plan = json.loads(PLAN.read_text())
    data,_,_,_,_ = prepare_data(base,EXTRAS,HISTORICAL,V4,CURRENT_POLLS,HISTORICAL_POLLS,plan)
    data["municipality_id"] = data.municipality_id.astype(str)
    typology = pd.read_parquet(ROOT/"data/processed/typologies/commune_typologies.parquet",
                              columns=["municipality_id","language_region","urban_rural","urban_rural_label"])
    typology["municipality_id"] = typology.municipality_id.astype(str)
    typology["urban_rural"] = typology.urban_rural.astype(str)
    counts = typology.urban_rural.value_counts().to_dict()
    if counts != {"1":509,"2":580,"3":1021}:
        raise ValueError(f"Unexpected OFS three-class codes/counts: {counts}")
    print("OFS_PROXY",typology.groupby(["urban_rural","urban_rural_label"]).size().to_json(),flush=True)
    typology["urban"] = typology.urban_rural.map(CROSSWALK)
    typology["language"] = typology.language_region.astype(str).map(REGIONS).fillna("other")
    eval_data = data[data.vote_date.ge("2016-01-01")].copy()
    eval_data = eval_data.merge(typology[["municipality_id","language","urban"]],on="municipality_id",how="left",validate="many_to_one")
    eval_data[["language","urban"]] = eval_data[["language","urban"]].fillna("other")
    eval_data["weight"] = (eval_data.statpop_pop_total*(1-eval_data.statpop_share_foreign)*(1-eval_data.statpop_share_0_19)).fillna(0)
    national = pd.read_csv(CURRENT_POLLS,dtype={"vote_key":str})
    regional = load_regional(ROOT/"data/external/polls_regional_v8/regional_polls.csv",national)
    settlement = load_settlement(acquisition/"settlement_polls.csv",national)
    rg = {str(k):v for k,v in regional.groupby("vote_key")}
    sg = {str(k):v for k,v in settlement.groupby("vote_key")}
    pg = {str(k):v.sort_values("municipality_id") for k,v in pred.groupby("vote_id")}
    cases = []
    for day,day_data in eval_data.groupby("vote_date",sort=True):
        for vote,v in day_data.groupby("vote_id",sort=False):
            v = v.sort_values("municipality_id")
            f = pg[str(vote)]
            if not np.array_equal(f.municipality_id.to_numpy(),v.municipality_id.to_numpy()) or not np.allclose(f.yes_share,v.yes_share):
                raise ValueError("Frozen prediction population mismatch")
            key = str(v.vote_key.iloc[0])
            lm = regional_target(rg.get(key,regional.iloc[:0]),str(day.date()),0.,"decided")
            um = latest_settlement(sg.get(key,settlement.iloc[:0]),str(day.date()))
            cases.append((str(vote),day,v,f,lm,um))
    if len(cases)!=66 or sum(len(c[2]) for c in cases)!=138868:
        raise ValueError("Incorrect spatial evaluation population")
    return data,cases


def score_row(vote,day,base,method,y,p,lm,um):
    result,_ = diagnostics(y,p,np.zeros(len(y),dtype=int),1)
    return {"vote_id":vote,"vote_date":str(day.date()),"variant":base+"__"+method,
            "base":base,"method":method,"mae_pp":result["mae"],"centered_mae":result["centered_mae"],
            "language_available":lm is not None,"urban_available":um is not None}


def summarize(records,reference):
    d = pd.DataFrame(records)
    out = []
    for name,g in d.groupby("variant",sort=False):
        if len(g)!=66 or g.vote_date.nunique()!=23:
            raise ValueError("Incomplete result")
        g24 = g[g.urban_available]
        out.append({"variant":name,"base":str(g.base.iloc[0]),"method":str(g.method.iloc[0]),
                    "mae":float(g.mae_pp.mean()),"centered_mae":float(g.centered_mae.mean()),
                    "covered_mae":float(g24.mae_pp.mean()),
                    "interval_vs_v8":[0.,0.] if name==reference else paired_date_bootstrap(d,reference,name)})
    return d,out


def run(base,acquisition,fusion,output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve previous run")
    _,cases = contexts(base,acquisition,fusion)
    records = []
    for vote,day,v,f,lm,um in cases:
        w,y = v.weight.to_numpy(float),v.yes_share.to_numpy(float)
        language,urban = v.language.to_numpy(),v.urban.to_numpy()
        a,z,b,indices = observation_system(w,language,urban,lm,um)
        for name in SPATIAL_BASES:
            p = f[name].to_numpy(float)
            preds = {"national":p,"language":gap_adjust(p,w,language,LANGUAGES,lm,1.) if lm is not None else p}
            for strength in (25,50,100):
                preds[f"urban{strength}"] = gap_adjust(p,w,urban,URBAN_LABELS,um,strength/100) if um is not None else p
            for method,ridge,weaker in (("joint_ridge10",.1,False),("joint_ridge30",.3,False),("joint_urban_weaker",.1,True)):
                preds[method] = joint_adjust(p,w,a,z,b,ridge,weaker,indices)
            for method,result in preds.items():
                records.append(score_row(vote,day,name,method,y,checked_prediction(p,w,result),lm,um))
    reference = "v8_reference__language"
    d,s = summarize(records,reference)
    if not np.isclose(next(r["mae"] for r in s if r["variant"]==reference),7.340163035010155,atol=.0002,rtol=0):
        raise ValueError("V8 reference changed")
    output.mkdir(parents=True,exist_ok=True)
    d.to_csv(output/"object_metrics.csv",index=False)
    pd.DataFrame(s).to_csv(output/"summary.csv",index=False)
    (output/"manifest.json").write_text(json.dumps({"status":"complete","strict_forecast_ready":False,
        "settlement_crosswalk":"OFS 2026 three-class proxy, not exact gfs.bern geography",
        "national_prediction_hash":sha(fusion/"national_predictions.parquet"),
        "summary":s},indent=2,allow_nan=False),encoding="utf-8")
    print("SUMMARY",json.dumps(s,allow_nan=False),flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("base","acquisition","fusion","output"):
        p.add_argument("--"+n,type=Path,required=True)
    a = p.parse_args()
    run(a.base,a.acquisition,a.fusion,a.output)


if __name__=="__main__":
    main()
