"""Matched V10.8 text and V10.9 income ablations with multiscale outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from threadpoolctl import threadpool_limits

from scripts.modeling.audit_xgboost_capacity import prepare_fold, reconstruct
from scripts.modeling.enrichment_experiment_v3 import baseline_features
from scripts.modeling.expectations_v101 import REFERENCE, multiscale
from scripts.modeling.income_v109 import TAX_FEATURES, TAX_MEAN_FEATURES
from scripts.modeling.local_profiles_v7 import fit_heads, historical_matrix, metric_basis
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.remaining_priorities_v9 import DEMO, centered_design, learn_exposures, text_features
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.semantic_training_v5 import PLAN
from scripts.modeling.spatial_margins_v81 import contexts, joint_adjust, observation_system
from scripts.modeling.temporal_drift_v6 import recency_weights
from scripts.modeling.turnout_v103 import load_ballots

METRICS = ("mae_pp","centered_mae_pp","national_mae_pp","canton_mae_pp")
TEXT_CONFIGS = (
    ("title_e5_16", "e5_title", 16, False),
    ("page_e5_16", "e5_document", 16, False),
    ("page_tfidf_16", "tfidf_document", 16, False),
    ("page_e5_cues_16", "e5_document", 16, True),
    ("cues_only", None, 0, True),
)
ECON_CONFIGS = {
    "demographic_control": DEMO,
    "income_means": TAX_MEAN_FEATURES,
    "income_distribution": TAX_FEATURES,
    "income_demographic": DEMO+TAX_FEATURES,
}


def income_lookup(data, income):
    rows=data[["vote_id","municipality_id","vote_date","statpop_pop_total","statpop_share_foreign","statpop_share_0_19"]].copy()
    rows["municipality_id"]=rows.municipality_id.astype(str)
    rows["year"]=rows.vote_date.dt.year-4
    rows["log_population"]=np.log1p(rows.statpop_pop_total)
    source=income.copy()
    source["municipality_id"]=source.municipality_id.astype(str)
    if source.duplicated(["municipality_id","year"]).any():
        raise ValueError("Duplicate income feature")
    rows=rows.merge(source[["municipality_id","year","available_from_proxy",*TAX_FEATURES]],
                    on=["municipality_id","year"],how="left",validate="many_to_one",sort=False)
    if (rows.available_from_proxy.notna() & rows.available_from_proxy.gt(rows.vote_date)).any():
        raise ValueError("Future income release proxy")
    return rows


def anchor(p,v,f,lm,um):
    w=v.weight.to_numpy(float)
    p=np.clip(p,0,1)
    if bool(v.poll_available.iloc[0]):
        p=shift_to(p,w,np.average(f.v8_reference.to_numpy(float),weights=w))
    a,z,b,i=observation_system(w,v.language.to_numpy(),v.urban.to_numpy(),lm,um)
    return joint_adjust(p,w,a,z,b,.1,True,i)


def run(base, acquisition, old_acquisition, fusion, output, suite):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve experiments")
    output.mkdir(parents=True,exist_ok=True)
    m=json.loads((acquisition/"manifest.json").read_text())
    if m["status"]!="complete":
        raise ValueError("Incomplete acquisition")
    prepared=json.loads((base/"data_manifest.json").read_text())
    numeric,categorical=baseline_features(prepared)
    plan=json.loads(PLAN.read_text())
    params=dict(plan["regressor_parameters"])
    data,cases=contexts(base,old_acquisition,fusion)
    data["municipality_id"]=data.municipality_id.astype(str)
    case_map={vote:(day,v,f,lm,um) for vote,day,v,f,lm,um in cases}
    outcomes=load_ballots()
    obs={k:g.set_index("municipality_id",verify_integrity=True) for k,g in outcomes.groupby("vote_id")}
    if suite=="text":
        path=acquisition/"text_corpus.parquet"
        if sha(path)!=m["text_corpus_sha256"] or sha(acquisition/"embeddings.npz")!=m["embedding"]["sha256"]:
            raise ValueError("Text source changed")
        corpus=pd.read_parquet(path).set_index("vote_id",verify_integrity=True)
        with np.load(acquisition/"embeddings.npz",allow_pickle=False) as z:
            emb={k:pd.DataFrame(z[k],index=z["vote_id"]) for k in ("title","document")}
        cue_cols=[c for c in corpus if "_cue_" in c]
    else:
        path=acquisition/"income_features.parquet"
        if sha(path)!=m["income_sha256"]:
            raise ValueError("Income source changed")
        exposures=income_lookup(data,pd.read_parquet(path))
    records,canton_rows,blocks,details=[],[],[],[]
    with threadpool_limits(limits=2):
        for window in plan["validation_windows"]:
            tr=data[data.vote_date.lt(window["start"])]
            ev=data[data.vote_date.between(window["start"],window["end"])].copy()
            if tr.vote_date.max()>=ev.vote_date.min():
                raise ValueError("Nonchronological fold")
            fold=prepare_fold(tr,ev,numeric,categorical,params)
            ids=fold["train_ids"]
            queries=fold["val_ids"]
            munis,mu,r=historical_matrix(tr,ids)
            dates=tr[["vote_id","vote_date"]].drop_duplicates().set_index("vote_id").vote_date
            rw=recency_weights(dates.loc[ids],window["start"],5)
            proto=ObjectProfileRegressor(numeric,categorical,**params)
            basis,heads=metric_basis(r,mu,rw,np.ones(len(munis)),5,params["random_state"])
            baseline=fit_heads(proto,fold["train_x"],heads,fold["val_x"])
            reference=reconstruct(baseline,basis,fold["val_idx"],fold["val_muni"])
            predictions={"reference":reference}
            if suite=="text":
                for tag,mode,n,use_cues in TEXT_CONFIGS:
                    a,b=text_features(corpus,ids,queries,mode,n,emb) if mode else (
                        np.empty((len(ids),0)),np.empty((len(queries),0)))
                    if use_cues:
                        a=np.column_stack([a,corpus.loc[ids,cue_cols].to_numpy(float)])
                        b=np.column_stack([b,corpus.loc[queries,cue_cols].to_numpy(float)])
                    tx=np.column_stack([fold["train_x"],a])
                    vx=np.column_stack([fold["val_x"],b])
                    h=fit_heads(proto,tx,heads,vx)
                    predictions[tag+"_all"]=reconstruct(h,basis,fold["val_idx"],fold["val_muni"])
                    h[:,0]=baseline[:,0]
                    predictions[tag+"_local"]=reconstruct(h,basis,fold["val_idx"],fold["val_muni"])
                details.append({"window":window["name"],"train_pages":int(corpus.loc[ids].usable_summary.sum()),
                                "validation_pages":int(corpus.loc[queries].usable_summary.sum())})
            else:
                t=exposures[exposures.vote_date.lt(window["start"])]
                e=exposures[exposures.vote_date.between(window["start"],window["end"])]
                vmap={str(k):g.set_index("municipality_id") for k,g in e.groupby("vote_id")}
                # Intersect training object support for fair comparison.
                coeff={}
                for tag,features in ECON_CONFIGS.items():
                    ix,c=learn_exposures(t,fold,r,basis,heads,features,False)
                    coeff[tag]=(ix,c)
                common=sorted(set.intersection(*(set(ix.tolist()) for ix,_ in coeff.values())))
                if len(common)<12:
                    raise ValueError("Insufficient matched exposure support")
                details.append({"window":window["name"],"common_training_objects":len(common),
                                "available_by_block":{k:len(v[0]) for k,v in coeff.items()}})
                for tag,features in ECON_CONFIGS.items():
                    ix,c=coeff[tag]
                    position={int(i):j for j,i in enumerate(ix)}
                    target=c[[position[i] for i in common]]
                    for lam in (30.,100.):
                        pred=Ridge(alpha=lam).fit(fold["train_x"][common],target).predict(fold["val_x"])
                        delta=np.zeros(len(ev))
                        for j,vote in enumerate(queries):
                            mask=fold["val_idx"]==j
                            mid=ev.loc[mask,"municipality_id"].to_numpy()
                            x,_=centered_design(vmap[vote].reindex(mid)[features].to_numpy(float))
                            delta[mask]=x@pred[j]
                        predictions[f"{tag}_{int(lam)}"]=np.clip(reference+delta,0,1)
            ordered=ev[["vote_id","municipality_id"]].copy()
            for name,p in predictions.items():
                ordered[name]=p
            for vote,g in ordered.groupby("vote_id"):
                day,v,f,lm,um=case_map[str(vote)]
                g=g.set_index("municipality_id").reindex(v.municipality_id)
                actual=obs[str(vote)].reindex(v.municipality_id)
                y=v.yes_share.to_numpy(float)
                yes,no=actual.votes_yes.to_numpy(float),actual.votes_no.to_numpy(float)
                w=v.weight.to_numpy(float)
                covered=bool(corpus.loc[str(vote),"usable_summary"]) if suite=="text" else True
                block=v[["vote_id","municipality_id","vote_date","yes_share"]].copy()
                for name in predictions:
                    q=anchor(g[name].to_numpy(float),v,f,lm,um)
                    met,cs=multiscale(y,q,w,yes,no,actual.canton.astype(str).to_numpy())
                    records.append({"variant":name,"vote_id":str(vote),"vote_date":str(day.date()),
                                    "fold":window["name"],"covered":covered,**met})
                    canton_rows.extend({"variant":name,"vote_id":str(vote),**c} for c in cs)
                    block[name]=q
                    block[name+"_weight"]=w
                blocks.append(block)
            print("FOLD",window["name"],list(predictions),flush=True)
    detail=pd.DataFrame(records)
    summaries=[]
    for name,g in detail.groupby("variant",sort=False):
        if len(g)!=66 or g.vote_date.nunique()!=23:
            raise ValueError("Wrong validation population")
        summaries.append({"variant":name,"objects":66,"covered_objects":int(g.covered.sum()),
                          **{k:float(g[k].mean()) for k in METRICS},
                          "covered_mae_pp":float(g.loc[g.covered,"mae_pp"].mean()) if g.covered.any() else None,
                          "gain_interval":[0.,0.] if name=="reference" else paired_date_bootstrap(detail,"reference",name)})
    if not np.isclose(summaries[0]["mae_pp"],REFERENCE,atol=.0002,rtol=0):
        raise ValueError(f"Frozen reference changed: {summaries[0]}")
    detail.to_csv(output/"object_metrics.csv",index=False)
    detail.groupby(["variant","fold"])[list(METRICS)].mean().to_csv(output/"fold_metrics.csv")
    pd.DataFrame(canton_rows).to_csv(output/"canton_metrics.csv",index=False)
    pd.DataFrame(summaries).to_csv(output/"summary.csv",index=False)
    all_preds=pd.concat(blocks,ignore_index=True)
    if len(all_preds)!=138868:
        raise ValueError("Wrong prediction population")
    all_preds.to_parquet(output/"predictions.parquet",index=False)
    result={"status":"complete","suite":suite,"strict_forecast_ready":False,
            "comparison_targets_loaded":False,"summary":summaries,"details":details,
            "acquisition_sha256":sha(acquisition/"manifest.json"),
            "prediction_sha256":sha(output/"predictions.parquet")}
    (output/"manifest.json").write_text(json.dumps(result,indent=2,allow_nan=False))
    print("SUMMARY",json.dumps(summaries,allow_nan=False),flush=True)
    print("DETAILS",json.dumps(details,allow_nan=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite",choices=["text","income"],required=True)
    for name in ("base","acquisition","old-acquisition","fusion","output"):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    run(a.base,a.acquisition,a.old_acquisition,a.fusion,a.output,a.suite)


if __name__=="__main__":
    main()
