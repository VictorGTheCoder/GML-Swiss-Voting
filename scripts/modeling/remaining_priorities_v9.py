"""V9 matched benchmark of text, economic interactions and complementary panels.

All predictions use frozen V8.1 survey anchoring. Separate suites test one new
information block at a time. Text matches are retrospective candidates, not
strictly admitted documents. The panel oracle is an explicit hindsight-only
diagnostic, never an input to a candidate forecast.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA, TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from threadpoolctl import threadpool_limits

from scripts.modeling.audit_xgboost_capacity import prepare_fold, reconstruct
from scripts.modeling.enrichment_experiment_v3 import baseline_features
from scripts.modeling.local_profiles_v7 import fit_heads, historical_matrix, metric_basis
from scripts.modeling.object_profile_v2 import ObjectProfileRegressor
from scripts.modeling.regional_anchor_v8 import shift_to
from scripts.modeling.semantic_poll_comparison_v4 import paired_date_bootstrap, sha
from scripts.modeling.semantic_training_v5 import PLAN
from scripts.modeling.spatial_margins_v81 import (
    checked_prediction,
    contexts,
    joint_adjust,
    observation_system,
    score_row,
)
from scripts.modeling.temporal_drift_v6 import recency_weights

REF = 7.229527497606818
ECON = ["econ_share_primary", "econ_share_secondary", "econ_share_tertiary",
        "econ_log_jobs", "econ_log_establishments"]
DEMO = ["statpop_share_foreign", "statpop_share_0_19", "log_population"]


def text_features(corpus, train_ids, eval_ids, mode, n, embeddings=None):
    """Fit vocabulary/compression on past objects only. Neural vectors are frozen."""
    tr, te = corpus.loc[train_ids], corpus.loc[eval_ids]
    field = "title_text" if "title" in mode else "document_text"
    if mode.startswith("tfidf"):
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5),
                                    min_df=2,max_features=12000,sublinear_tf=True)
        a = vectorizer.fit_transform(tr[field])
        b = vectorizer.transform(te[field])
        svd = TruncatedSVD(n_components=min(n,a.shape[0]-1,a.shape[1]-1),random_state=20261124)
        a,b = svd.fit_transform(a),svd.transform(b)
    else:
        if embeddings is None:
            raise ValueError("Neural embeddings unavailable")
        vectors = embeddings["title" if field=="title_text" else "document"]
        a,b = vectors.loc[train_ids].to_numpy(),vectors.loc[eval_ids].to_numpy()
        pca=PCA(n_components=min(n,len(a)-1,a.shape[1]),random_state=20261124)
        a,b=pca.fit_transform(a),pca.transform(b)
    # Rescale with TRAIN statistics (especially for linear heads).
    m,s=a.mean(axis=0),a.std(axis=0).clip(min=1e-8)
    a,b=(a-m)/s,(b-m)/s
    if field=="document_text":
        a=np.column_stack([a,tr.usable_summary.to_numpy(float)])
        b=np.column_stack([b,te.usable_summary.to_numpy(float)])
    return a,b


def economic_lookup(data,econ):
    """Join reference year only; never use a later year or invent suppressed cells."""
    result=data[["vote_id","municipality_id","vote_date","statpop_pop_total",
                 "statpop_share_foreign","statpop_share_0_19"]].copy()
    result["municipality_id"]=result.municipality_id.astype(str)
    result["year"]=result.vote_date.dt.year-2
    result["log_population"]=np.log1p(result.statpop_pop_total)
    if econ is None:
        for c in ECON:
            result[c]=np.nan
        return result
    if econ.duplicated(["municipality_id","year"]).any():
        raise ValueError("Duplicate economic source row")
    econ=econ.copy()
    econ["municipality_id"]=econ.municipality_id.astype(str)
    result=result.merge(econ[["municipality_id","year","available_from_proxy",*ECON]],
                        on=["municipality_id","year"],how="left",validate="many_to_one",sort=False)
    if (result.available_from_proxy.notna()&result.available_from_proxy.gt(result.vote_date)).any():
        raise ValueError("Economic release proxy after vote")
    return result


def centered_design(x):
    """Cross-sectional centering with missing values neutral only in model space."""
    x=np.asarray(x,float)
    valid=np.isfinite(x)
    count=valid.sum(axis=0)
    mean=np.divide(np.nansum(x,axis=0),count,out=np.zeros(x.shape[1]),where=count>0)
    centered=np.where(valid,x-mean,0.)
    scale=np.sqrt(np.divide(np.square(centered).sum(axis=0),count,
                            out=np.ones(x.shape[1]),where=count>0)).clip(min=1e-8)
    return centered/scale,valid


def learn_exposures(train_rows, fold, residuals, basis, targets, features, econ_present):
    """Learn object-specific coefficients for local variation unexplained by PCA.

    Training target is residual after the observed training object is projected
    onto the historical PCA. Per-object regressions use only that object's
    aggregate municipal outcomes. Outer evaluation outcomes never enter fit.
    """
    by_vote={str(k):g for k,g in train_rows.groupby("vote_id",sort=False)}
    # Align columns with historical_matrix's sorted municipal columns.
    munis=sorted(train_rows.municipality_id.unique())
    coefficients,indices=[],[]
    historical_profile=basis.mean_[None,:]+targets[:,1:]@basis.components_
    for i,vote in enumerate(fold["train_ids"]):
        g=by_vote[vote].set_index("municipality_id").reindex(munis)
        x,valid=centered_design(g[features].to_numpy(float))
        observed=np.isfinite(residuals[i])
        coverage=valid[observed].mean() if observed.any() else 0.
        # Compare only votes with enough actual covariate support.
        if coverage<.7 or (econ_present and int(g.year.dropna().iloc[0])<2011):
            continue
        r=residuals[i,observed]-historical_profile[i,observed]
        x=x[observed]
        coef=np.linalg.solve(x.T@x+100*np.eye(x.shape[1]),x.T@r)
        coefficients.append(coef)
        indices.append(i)
    return np.asarray(indices,dtype=int),np.asarray(coefficients)


def panel_indices(loadings, eligible, k, seed=None):
    """Greedy D-optimal choice with intercept, using past basis loadings only."""
    a=np.asarray(loadings,float)
    eligible=np.flatnonzero(eligible)
    if k>len(eligible) or k<a.shape[1]+1:
        raise ValueError("Insufficient panel support")
    if seed is not None:
        return np.random.default_rng(seed).choice(eligible,size=k,replace=False)
    scaled=a*np.sqrt(len(a))
    x=np.column_stack([np.ones(len(a)),scaled])
    precision=np.eye(x.shape[1])*.01
    chosen=[]
    pool=eligible.copy()
    for _ in range(k):
        inverse=np.linalg.inv(precision)
        gain=np.einsum("ij,jk,ik->i",x[pool],inverse,x[pool])
        j=int(np.argmax(gain))
        selected=pool[j]
        chosen.append(selected)
        precision+=np.outer(x[selected],x[selected])
        pool=np.delete(pool,j)
    return np.asarray(chosen)


def reconstruct_panel(shares, panel_basis, center, rank_basis, penalty=.05):
    """Estimate level and latent coefficients from predicted or diagnostic panel.

    Unpenalized intercept and a ridge on coefficients, with fixed train basis.
    """
    a=np.column_stack([np.ones(len(panel_basis)),panel_basis*np.sqrt(len(rank_basis))])
    regularization=np.diag([0.]+[penalty]*panel_basis.shape[1])
    coefficients=np.linalg.solve(a.T@a+regularization,a.T@(shares-center))
    return coefficients[0],coefficients[1:]*np.sqrt(len(rank_basis))


def panel_heads(proto, x, y, val_x, indices):
    result=[]
    for j in indices:
        observed=np.isfinite(y[:,j])
        if observed.sum()<30:
            raise ValueError("Panel commune lacks historical outcomes")
        model=proto._make_regressor()
        model.fit(x[observed],y[observed,j])
        result.append(model.predict(val_x))
    return np.column_stack(result)


def score_predictions(vote,day,v,f,lm,um,variant,structural,*,oracle=False):
    y,w=v.yes_share.to_numpy(float),v.weight.to_numpy(float)
    p=np.clip(np.asarray(structural,float),0,1)
    if not oracle and bool(v.poll_available.iloc[0]):
        p=shift_to(p,w,np.average(f.v8_reference.to_numpy(float),weights=w))
    if not oracle:
        a,z,b,i=observation_system(w,v.language.to_numpy(),v.urban.to_numpy(),lm,um)
        p=checked_prediction(p,w,joint_adjust(p,w,a,z,b,.1,True,i))
    row=score_row(vote,day,"v9",variant,y,p,lm,um)
    row["variant"]=variant
    row["oracle"]=oracle
    return row


def run(base,acquisition,old_acquisition,fusion,output,suite):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Preserve prior experiment")
    output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((acquisition/"manifest.json").read_text())
    prepared=json.loads((base/"data_manifest.json").read_text())
    numeric,categorical=baseline_features(prepared)
    plan=json.loads(PLAN.read_text())
    params=dict(plan["regressor_parameters"])
    data,cases=contexts(base,old_acquisition,fusion)
    case_map={vote:(day,v,f,lm,um) for vote,day,v,f,lm,um in cases}
    data["municipality_id"]=data.municipality_id.astype(str)
    corpus=emb=None
    if suite=="text":
        if sha(acquisition/"text_corpus.parquet")!=manifest["text_corpus_sha256"]:
            raise ValueError("Text corpus changed")
        corpus=pd.read_parquet(acquisition/"text_corpus.parquet").set_index("vote_id",verify_integrity=True)
        if manifest.get("embedding",{}).get("sha256"):
            path=acquisition/"embeddings.npz"
            if sha(path)!=manifest["embedding"]["sha256"]:
                raise ValueError("Embedding artifact changed")
            with np.load(path,allow_pickle=False) as z:
                emb={c:pd.DataFrame(z[c],index=z["vote_id"]) for c in ("title","document")}
    econ=None
    if suite=="economy":
        if manifest.get("economy",{}).get("sha256"):
            path=acquisition/"economic_features.parquet"
            if sha(path)!=manifest["economy"]["sha256"]:
                raise ValueError("Economic artifact changed")
            econ=pd.read_parquet(path)
        exposures=economic_lookup(data,econ)
    rows,extra=[],[]
    for window in plan["validation_windows"]:
        train=data[data.vote_date.lt(window["start"])]
        evaluation=data[data.vote_date.between(window["start"],window["end"])].copy()
        if train.empty or train.vote_date.max()>=evaluation.vote_date.min():
            raise ValueError("Invalid chronology")
        fold=prepare_fold(train,evaluation,numeric,categorical,params)
        munis,mu,residuals=historical_matrix(train,fold["train_ids"])
        dates=train[["vote_id","vote_date"]].drop_duplicates().set_index("vote_id").vote_date
        w=recency_weights(dates.loc[fold["train_ids"]],window["start"],5)
        proto=ObjectProfileRegressor(numeric,categorical,**params)
        with threadpool_limits(limits=2):
            basis,targets=metric_basis(residuals,mu,w,np.ones(len(munis)),5,params["random_state"])
            predicted=fit_heads(proto,fold["train_x"],targets,fold["val_x"])
            reference=reconstruct(predicted,basis,fold["val_idx"],fold["val_muni"])
            predictions={"reference":reference}
            if suite=="text":
                configs=[("tfidf_title",8),("tfidf_document",8)]
                if emb is not None:
                    configs += [("e5_title",8),("e5_document",8),("e5_document",16)]
                for mode,n in configs:
                    a,b=text_features(corpus,fold["train_ids"],fold["val_ids"],mode,n,emb)
                    tx=np.column_stack([fold["train_x"],a])
                    vx=np.column_stack([fold["val_x"],b])
                    h=fit_heads(proto,tx,targets,vx)
                    predictions[f"{mode}_{n}_all"]=reconstruct(h,basis,fold["val_idx"],fold["val_muni"])
                    h[:,0]=predicted[:,0]
                    predictions[f"{mode}_{n}_local"]=reconstruct(h,basis,fold["val_idx"],fold["val_muni"])
                    # Regularized combination with the existing structural heads.
                    ridge=Ridge(alpha=100).fit(tx,targets[:,1:]).predict(vx)
                    h=predicted.copy()
                    h[:,1:]=.5*h[:,1:]+.5*ridge
                    predictions[f"{mode}_{n}_ridgeblend"]=reconstruct(h,basis,fold["val_idx"],fold["val_muni"])
                extra.append({"window":window["name"],"train_summary":int(corpus.loc[fold["train_ids"]].usable_summary.sum()),
                              "validation_summary":int(corpus.loc[fold["val_ids"]].usable_summary.sum())})
            elif suite=="economy":
                train_rows=exposures[exposures.vote_date.lt(window["start"])]
                valid_rows=exposures[exposures.vote_date.between(window["start"],window["end"])]
                vmap={str(k):g.set_index("municipality_id") for k,g in valid_rows.groupby("vote_id")}
                blocks={"demographic_control":DEMO}
                if econ is not None:
                    blocks.update({"economy":ECON,"demographic_economy":DEMO+ECON})
                for mode,features in blocks.items():
                    ix,c=learn_exposures(train_rows,fold,residuals,basis,targets,features,mode!="demographic_control")
                    if len(ix)<12:
                        raise ValueError(f"Insufficient historical covariate support {mode}: {len(ix)}")
                    extra.append({"window":window["name"],"mode":mode,"train_objects":len(ix)})
                    for lam in (30.,100.):
                        coeff=Ridge(alpha=lam).fit(fold["train_x"][ix],c).predict(fold["val_x"])
                        adjustment=np.zeros(len(evaluation))
                        for j,vote in enumerate(fold["val_ids"]):
                            mask=fold["val_idx"]==j
                            m=evaluation.loc[mask,"municipality_id"].to_numpy()
                            x,_=centered_design(vmap[vote].reindex(m)[features].to_numpy(float))
                            adjustment[mask]=x@coeff[j]
                        predictions[f"{mode}_{int(lam)}"]=np.clip(reference+adjustment,0,1)
            else:
                loadings=basis.components_.T
                eligible=np.isfinite(residuals).mean(axis=0)>=.95
                for k in (10,20):
                    for method in ("diverse","random"):
                        chosen=panel_indices(loadings,eligible,k,seed=20261124+k if method=="random" else None)
                        extra.append({"window":window["name"],"method":method,"k":k,"communes":munis[chosen].tolist()})
                        observed_history=residuals+mu[:,None]
                        fitted=panel_heads(proto,fold["train_x"],observed_history,fold["val_x"],chosen)
                        h=predicted.copy()
                        for j in range(len(fold["val_ids"])):
                            level,coef=reconstruct_panel(fitted[j],loadings[chosen],basis.mean_[chosen],loadings)
                            h[j,0]=level
                            h[j,1:]=coef
                        predictions[f"panel_{method}_{k}"]=reconstruct(h,basis,fold["val_idx"],fold["val_muni"])
                        h[:,0]=predicted[:,0]
                        predictions[f"panel_{method}_{k}_local"]=reconstruct(h,basis,fold["val_idx"],fold["val_muni"])
                        # Explicit oracle: measured held-out panel only, not a forecast.
                        oracle=predicted.copy()
                        coverage=[]
                        for j,vote in enumerate(fold["val_ids"]):
                            day,v,f,lm,um=case_map[vote]
                            actual=v.set_index("municipality_id").yes_share.reindex(munis[chosen]).to_numpy(float)
                            present=np.isfinite(actual)
                            if present.sum()<6:
                                raise ValueError("Oracle panel has too few observed municipalities")
                            level,coef=reconstruct_panel(actual[present],loadings[chosen[present]],
                                                         basis.mean_[chosen[present]],loadings)
                            oracle[j,0]=level
                            oracle[j,1:]=coef
                            coverage.append(int(present.sum()))
                        predictions[f"oracle_panel_{method}_{k}"]=reconstruct(oracle,basis,fold["val_idx"],fold["val_muni"])
                        extra[-1]["minimum_observed_oracle_panel"]=min(coverage)
        # Restore exact row keys, then use unchanged V8.1 geographic correction.
        ordered=evaluation[["vote_id","municipality_id"]].copy()
        for variant,p in predictions.items():
            ordered[variant]=p
        for vote,group in ordered.groupby("vote_id"):
            day,v,f,lm,um=case_map[str(vote)]
            g=group.set_index("municipality_id").reindex(v.municipality_id)
            if g.reference.isna().any():
                raise ValueError("Prediction keys mismatch")
            for variant in predictions:
                rows.append(score_predictions(str(vote),day,v,f,lm,um,variant,g[variant].to_numpy(float),
                                              oracle=variant.startswith("oracle_")))
        print("FOLD",window["name"],"variants",list(predictions),flush=True)
    detail=pd.DataFrame(rows)
    summary=[]
    for name,g in detail.groupby("variant",sort=False):
        if len(g)!=66 or g.vote_date.nunique()!=23:
            raise ValueError("Incomplete variant")
        summary.append({"variant":name,"mae":float(g.mae_pp.mean()),
                        "centered_mae":float(g.centered_mae.mean()),
                        "oracle":bool(g.oracle.iloc[0]),
                        "gain_interval":[0.,0.] if name=="reference" else paired_date_bootstrap(detail,"reference",name)})
    if not np.isclose(next(r["mae"] for r in summary if r["variant"]=="reference"),REF,atol=.0002,rtol=0):
        raise ValueError(f"V8.1 reference changed: {summary[0]}")
    detail.to_csv(output/"object_metrics.csv",index=False)
    pd.DataFrame(summary).to_csv(output/"summary.csv",index=False)
    (output/"manifest.json").write_text(json.dumps({"status":"complete","suite":suite,"strict_forecast_ready":False,
        "acquisition_sha256":sha(acquisition/"manifest.json"),"summary":summary,"details":extra},indent=2,allow_nan=False))
    print("SUMMARY",json.dumps(summary,allow_nan=False),flush=True)
    print("DETAILS",json.dumps(extra,allow_nan=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("base","acquisition","old-acquisition","fusion","output"):
        p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--suite",choices=("text","economy","panels"),required=True)
    a=p.parse_args()
    run(a.base,a.acquisition,a.old_acquisition,a.fusion,a.output,a.suite)


if __name__=="__main__":
    main()
