"""Stage 02: national-level poll coverage and chronological institute fusion.

The frozen V7 structural profile stays unchanged. A retrospective LeeWas
last-poll appendix is a weaker provenance tier; no exact date is fabricated.
Use only past completed dates for institute weights and calibration errors.
All variants retain the original 66-object equal-municipality MAE metric.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.audit_xgboost_capacity import diagnostics
from scripts.modeling.poll_calibration_v8 import prior_poll_data
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
    load_expanded_polls,
    prepare_data,
)

VARIANTS = (
    "v8_reference",
    "ssr_extended",
    "ssr_extended_tamedia_fallback",
    "ssr_latest_tamedia_fallback",
    "tamedia_latest",
    "blend25",
    "blend50",
    "blend75",
    "blend_latest50",
    "blend_borrowed_trend50",
    "adaptive_mse",
    "adaptive_bias_mse",
    "consensus_disagreement_shrink",
)
# Fixed candidates carried forward, not selected by validation scores.
SPATIAL_BASES = ("v8_reference", "ssr_extended_tamedia_fallback", "blend50",
                 "blend_borrowed_trend50", "adaptive_mse", "adaptive_bias_mse")


def pair_forecast(row, date):
    """Yes-only trend from explicitly reported historical waves."""
    day = pd.Timestamp(date)
    a, b = pd.Timestamp(row.first_midpoint), pd.Timestamp(row.last_midpoint)
    publication = pd.Timestamp(row.last_published_date)
    if not a < b <= publication < day:
        raise ValueError("Invalid pre-vote historical pair")
    if publication > day - pd.Timedelta(days=1):
        raise ValueError("Publication misses the day-before cutoff")
    last = float(row.last_yes) / 100
    first = float(row.first_yes) / 100
    delta = float(np.clip((last-first)*(day-b).days/(b-a).days, -.15, .15))
    delta = float(np.clip(delta, -last, 1-last))
    return last, delta


def fit_fusion(history, use_bias=False):
    """Learn a convex weight on two correlated institute errors, shrunk to .5.

    History is one record per *past* polled vote. Bias correction is shrunk
    toward zero; the covariance of errors, not sample sizes, drives fusion.
    Prior penalty is equivalent to eight pseudo-votes with 8 pp errors.
    """
    if len(history) < 8:
        return .5, np.zeros(2)
    errors = np.asarray(history, float)
    if errors.ndim != 2 or errors.shape[1] != 2 or not np.isfinite(errors).all():
        raise ValueError("Fusion history must contain paired finite errors")
    n = len(errors)
    bias = errors.sum(axis=0)/(n+8) if use_bias else np.zeros(2)
    centered = errors - bias
    difference = centered[:,0]-centered[:,1]
    prior = 8 * .08**2
    weight = (-difference @ centered[:,1] + prior*.5)/(difference@difference+prior)
    return float(np.clip(weight, .1, .9)), bias


def target_table(old_anchor, last, delta, tamedia, weights, structural_mean):
    """Predictions only; a missing source never becomes an invented survey."""
    trend = None if last is None else float(np.clip(last+delta, 0, 1))
    if trend is None and tamedia is None:
        return dict.fromkeys(VARIANTS, structural_mean)
    both = trend is not None and tamedia is not None
    s = trend if trend is not None else tamedia
    t = tamedia if tamedia is not None else s
    latest = last if last is not None else t
    weight, _ = weights[0]
    weight_bias, bias = weights[1]
    out = {
        "v8_reference": old_anchor,
        "ssr_extended": trend if trend is not None else structural_mean,
        "ssr_extended_tamedia_fallback": s,
        "ssr_latest_tamedia_fallback": latest,
        "tamedia_latest": t,
        "blend25": .25*s+.75*t,
        "blend50": .5*s+.5*t,
        "blend75": .75*s+.25*t,
        "blend_latest50": .5*latest+.5*t,
        # SSR trend borrowed for Tamedia with attenuation; not an observed
        # second Tamedia wave, and not an exact common-time trend.
        "blend_borrowed_trend50": .5*s+.5*np.clip(t + .5*delta,0,1) if both else s,
        "adaptive_mse": weight*s+(1-weight)*t,
        "adaptive_bias_mse": weight_bias*(s-bias[0])+(1-weight_bias)*(t-bias[1]) if both else s,
        "consensus_disagreement_shrink": .5*(s+t) if both and abs(s-t)<=.12 else
          (.75*.5*(s+t)+.25*structural_mean if both else s),
    }
    return {k: float(np.clip(v, 0, 1)) for k,v in out.items()}


def run(base, prediction_dir, acquisition, output):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve previous experiments")
    acq = json.loads((acquisition/"manifest.json").read_text(encoding="utf-8"))
    for name in ("national_latest.csv", "national_pairs.csv"):
        if sha(acquisition/name) != acq["hashes"][name]:
            raise ValueError("Acquisition artifact changed")
    latest = pd.read_csv(acquisition/"national_latest.csv", dtype={"vote_key":str}).set_index("vote_key")
    pairs = pd.read_csv(acquisition/"national_pairs.csv", dtype={"vote_key":str}).set_index("vote_key")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    data, _, _, _, _ = prepare_data(base, EXTRAS, HISTORICAL, V4, CURRENT_POLLS, HISTORICAL_POLLS, plan)
    data = data[data.vote_date.ge("2016-01-01")].copy()
    national = load_expanded_polls(CURRENT_POLLS, HISTORICAL_POLLS)
    national["vote_key"] = national.vote_key.astype(str)
    regional = load_regional(
        ROOT/"data/external/polls_regional_v8/regional_polls.csv",
        pd.read_csv(CURRENT_POLLS, dtype={"vote_key":str}),
    )
    typology = pd.read_parquet(ROOT/"data/processed/typologies/commune_typologies.parquet",
                              columns=["municipality_id","language_region"])
    typology["municipality_id"] = typology.municipality_id.astype(str)
    data["municipality_id"] = data.municipality_id.astype(str)
    data = data.merge(typology,on="municipality_id",how="left",validate="many_to_one")
    data["language"] = data.language_region.astype(str).map(REGIONS).fillna("other")
    data["weight"] = (data.statpop_pop_total*(1-data.statpop_share_foreign)*
                      (1-data.statpop_share_0_19)).fillna(0)
    manifest = json.loads((prediction_dir/"manifest.json").read_text(encoding="utf-8"))
    ppath = prediction_dir/"pca_recent5_predictions.parquet"
    if sha(ppath) != manifest["prediction_hashes"]["pca_recent5"]:
        raise ValueError("Frozen predictions changed")
    pred = pd.read_parquet(ppath)
    pred["vote_id"] = pred.vote_id.astype(str)
    pred["municipality_id"] = pred.municipality_id.astype(str)
    if len(pred)!=138868 or pred.vote_date.ge("2023-01-01").any():
        raise ValueError("Wrong evaluation population")
    pred_by_vote = {str(k):v.sort_values("municipality_id") for k,v in pred.groupby("vote_id")}
    old_by_vote = {str(k):v for k,v in national.groupby("vote_key")}
    reg_by_vote = {str(k):v for k,v in regional.groupby("vote_key")}
    history, records, target_rows, forecast_rows = [], [], [], []
    population = set()
    for day, same_day in data.groupby("vote_date",sort=True):
        weights = (fit_fusion(history),fit_fusion(history,use_bias=True))
        next_history = []
        for vote, v in same_day.groupby("vote_id",sort=False):
            vote = str(vote)
            v = v.sort_values("municipality_id")
            if vote not in pred_by_vote:
                raise ValueError("Unexpected target object")
            frame = pred_by_vote[vote]
            key = str(v.vote_key.iloc[0])
            if not np.array_equal(frame.municipality_id.to_numpy(),v.municipality_id.to_numpy()):
                raise ValueError("Keys mismatch")
            if pd.Timestamp(latest.loc[key,"vote_date"]) != day:
                raise ValueError("Poll metadata date mismatch")
            w = v.weight.to_numpy(float)
            y = v.yes_share.to_numpy(float)
            if w.sum()<=0 or not np.allclose(y,frame.yes_share):
                raise ValueError("Invalid target or municipal proxy")
            p = frame.prediction.to_numpy(float)
            structural = frame.structural_prediction.to_numpy(float)
            old = prior_poll_data(old_by_vote.get(key,national.iloc[:0]),day)
            srg_latest, delta = None, 0.
            if old is not None:
                srg_latest, delta = old["yes"], old["delta"]
                if abs(np.average(p,weights=w)-old["frozen"])>1e-7:
                    raise ValueError("Original national anchoring changed")
            elif key in pairs.index:
                srg_latest, delta = pair_forecast(pairs.loc[key],day)
            elif key!="6030":
                raise ValueError("Missing primary survey pair")
            tamedia = float(latest.loc[key,"tamedia_yes"])/100
            target = target_table(np.average(p,weights=w),srg_latest,delta,tamedia,
                                  weights,np.average(structural,weights=w))
            region = regional_target(reg_by_vote.get(key,regional.iloc[:0]),
                                     str(day.date()),0.,"decided")
            language = v.language.astype(str).to_numpy()
            national_forecasts = {}
            for name, value in target.items():
                if name=="v8_reference":
                    anchored = p.copy()
                elif name=="ssr_extended" and srg_latest is None:
                    anchored = structural.copy()
                else:
                    anchored = shift_to(structural,w,value)
                national_forecasts[name] = anchored
            frozen = frame[["vote_id","municipality_id","vote_date","yes_share"]].copy()
            for name, anchored in national_forecasts.items():
                if name in SPATIAL_BASES:
                    frozen[name]=anchored
                adjusted = (gap_adjust(anchored,w,language,LANGUAGES,region,1.)
                            if region is not None else anchored)
                before,_ = diagnostics(y,anchored,np.zeros(len(y),dtype=int),1)
                after,_ = diagnostics(y,adjusted,np.zeros(len(y),dtype=int),1)
                records.append({"variant":name,"vote_id":vote,"vote_date":str(day.date()),
                                "mae_pp":after["mae"],"national_only_mae":before["mae"],
                                "centered_mae":after["centered_mae"],
                                "added_srg":key in pairs.index,"old_srg":old is not None,
                                "regional_available":region is not None})
                if abs(np.average(adjusted-anchored,weights=w))>1e-8:
                    raise ValueError("Regional calibration moved national mean")
            forecast_rows.append(frozen)
            target_rows.append({"vote_id":vote,"vote_date":str(day.date()),"prior_pairs":len(history),
                                "srg_weight":weights[0][0],"bias_weight":weights[1][0],
                                "bias_srg":float(weights[1][1][0]),"bias_tamedia":float(weights[1][1][1]),
                                "srg_latest":srg_latest,"srg_trend":delta,"tamedia_latest":tamedia,
                                **target})
            population.add(vote)
            if srg_latest is not None:
                actual=float(np.average(y,weights=w))
                next_history.append([float(np.clip(srg_latest+delta,0,1))-actual,tamedia-actual])
        # All predictions on a date were fixed with the same prior.
        history.extend(next_history)
    detail=pd.DataFrame(records)
    if len(population)!=66 or detail.vote_date.nunique()!=23:
        raise ValueError("Wrong validation population")
    summary=[]
    for name,g in detail.groupby("variant",sort=False):
        if len(g)!=66:
            raise ValueError("Incomplete variant")
        new=g[g.added_srg]
        r={"variant":name,"mae":float(g.mae_pp.mean()),
           "national_only_mae":float(g.national_only_mae.mean()),
           "centered_mae":float(g.centered_mae.mean()),
           "new_ssr_mae":float(new.mae_pp.mean()),
           "interval_vs_v8":[0.,0.] if name=="v8_reference" else paired_date_bootstrap(detail,"v8_reference",name)}
        summary.append(r)
    baseline=next(r for r in summary if r["variant"]=="v8_reference")
    if not np.isclose(baseline["mae"],7.340163035010155,atol=.0002,rtol=0):
        raise ValueError("V8 reference not reproduced")
    output.mkdir(parents=True,exist_ok=True)
    detail.to_csv(output/"object_metrics.csv",index=False)
    pd.DataFrame(summary).to_csv(output/"summary.csv",index=False)
    pd.DataFrame(target_rows).to_csv(output/"national_targets.csv",index=False)
    pd.concat(forecast_rows,ignore_index=True).to_parquet(output/"national_predictions.parquet",index=False)
    out={"status":"complete","strict_forecast_ready":False,"comparison_targets_loaded":False,
         "prediction_hash":sha(output/"national_predictions.parquet"),"acquisition_sha":sha(acquisition/"manifest.json"),
         "same_date_excluded":True,"summary":summary}
    (output/"manifest.json").write_text(json.dumps(out,indent=2,allow_nan=False),encoding="utf-8")
    print("SUMMARY",json.dumps(summary,allow_nan=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("base","predictions","acquisition","output"):
        parser.add_argument("--"+name,required=True,type=Path)
    a=parser.parse_args()
    run(a.base,a.predictions,a.acquisition,a.output)


if __name__=="__main__":
    main()
