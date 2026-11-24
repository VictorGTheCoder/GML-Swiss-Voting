"""V10.9: official AFC/ESTV aggregate tax indicators and audited geography.

The source introduction specifies the 1 January geography of each tax year.
Use original municipality codes, verify against independent OFS snapshots,
and follow mutations. Medians and Gini are not additively aggregable.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.acquire_v9 import MUTATIONS_URL, digest, download, norm
from scripts.repertoire_communes.commune_crosswalk import load_mutations, resolve

SNAPSHOT_URL = "https://www.agvchapp.bfs.admin.ch/api/communes/snapshot"
INTRO = "https://www.estv.admin.ch/dam/de/sd-web/StGxoQeMhCYk/statistik-dbst-np-kennzahlen-ohne-einleitung-de.pdf"
MEANS = ["mean_steink","mean_steinka","mean_reink","mean_stbetr"]
NONSUM = ["median_steinka","gini_steinka","median_steink"]
TAX_FEATURES = ["tax_"+x for x in MEANS+NONSUM]
TAX_MEAN_FEATURES = ["tax_"+x for x in MEANS]


def aggregate_group(g, expected):
    """Counts weighted means; do not invent median or inequality after merges."""
    n = g.stpf.to_numpy(float)
    if len(g)!=expected or not np.isfinite(n).all() or (n<=0).any():
        return None
    row={"tax_units":float(n.sum()),"predecessors":int(expected)}
    for col in MEANS:
        x=g[col].to_numpy(float)
        row["tax_"+col]=float(np.average(x,weights=n)) if np.isfinite(x).all() else np.nan
    for col in NONSUM:
        row["tax_"+col]=float(g[col].iloc[0]) if expected==1 else np.nan
    return row


def read_source(path):
    raw=pd.read_excel(path,sheet_name="Gemeinden - Communes",engine="openpyxl")
    cols=["gdenr","gdename","Einheit","stpf",*MEANS,*NONSUM]
    if not set(cols).issubset(raw):
        raise ValueError("Unexpected AFC schema")
    raw=raw.loc[raw.Einheit.eq("Total"),cols].copy()
    code=pd.to_numeric(raw.gdenr,errors="coerce")
    raw=raw.loc[code.notna() & code.gt(0) & code.lt(10000)].copy()
    raw["code"]=pd.to_numeric(raw.gdenr).astype(int).astype(str)
    if raw.code.duplicated().any() or len(raw)<2000:
        raise ValueError("Unexpected AFC municipality keys")
    for col in ["stpf",*MEANS,*NONSUM]:
        raw[col]=pd.to_numeric(raw[col],errors="coerce")
    raw.loc[~raw.gini_steinka.between(0,1),"gini_steinka"]=np.nan
    return raw


def name_code_match(year, source, official):
    """2012 AFC workbook names have their high bits stripped (audited).
    
    Admit a corrupted name only when the municipality code identifies the
    official roster entry AND its exact deterministic corruption matches.
    """
    if norm(source)==norm(official):
        return True,False
    if year==2012 and str(source)==''.join(chr(ord(c)&127) for c in str(official)):
        return True,True
    return False,False


def acquire(input_dir,output,geography=None):
    records=json.loads((input_dir/"income_inventory.json").read_text())
    output.mkdir(parents=True,exist_ok=True)
    years=sorted(int(r["year"]) for r in records if "sha256" in r)
    if years!=list(range(2003,2019)):
        raise ValueError("Expected 16 audited annual files")
    mp=output/"mutations.csv"
    prior=json.loads((geography/"manifest.json").read_text()) if geography is not None else None
    if prior is None:
        prov=download(MUTATIONS_URL,mp,{"includeTerritoryExchange":"false","startPeriod":"01-01-2003","endPeriod":"01-01-2026","useBfsCode":"true"})
    else:
        prov=prior["mutations"]
        mp.write_bytes((geography/"mutations.csv").read_bytes())
        if digest(mp)!=prov["sha256"]:
            raise ValueError("Cached mutations hash mismatch")
    mutations=load_mutations(mp)
    geo=pd.read_parquet(ROOT/"data/processed/typologies/commune_typologies.parquet",columns=["municipality_id"])
    target=set(geo.municipality_id.astype(str))
    def snapshot(year):
        path=output/f"snapshot_{year}.csv"
        if prior is None:
            info=download(SNAPSHOT_URL,path,{"date":f"01-01-{year}","useBfsCode":"true"})
        else:
            info=next(r["snapshot"] for r in prior["year_audit"] if r["year"]==year)
            path.write_bytes((geography/path.name).read_bytes())
            if digest(path)!=info["sha256"]:
                raise ValueError("Cached snapshot hash mismatch")
        return year,path,info
    with ThreadPoolExecutor(max_workers=4) as pool:
        snapshots={y:(p,i) for y,p,i in pool.map(snapshot,years)}
    results,report=[],[]
    for rec in records:
        y=int(rec["year"])
        path=input_dir/f"income_{y}.xlsx"
        if digest(path)!=rec["sha256"]:
            raise ValueError("Source workbook hash changed")
        raw=read_source(path)
        sp,si=snapshots[y]
        s=pd.read_csv(sp,dtype=str,encoding="utf-8-sig")
        s=s[s.Level.eq("3")].copy()
        s["code"]=s.BfsCode.astype(int).astype(str)
        if s.code.duplicated().any():
            raise ValueError("Duplicate snapshot keys")
        names=s.set_index("code").Name.to_dict()
        # Source code must exist in that year's official geographic roster.
        # Name comparison is audited (strict identity after normalisation).
        checks=[name_code_match(y,n,names[c]) if c in names else (False,False) for c,n in zip(raw.code,raw.gdename)]
        raw["name_ok"]=[v[0] for v in checks]
        encoding_recovered=sum(v[1] for v in checks)
        expected={}
        blocked=set()
        mapping={}
        for c in names:
            targets={str(int(t)).zfill(4) for t in resolve(c,date(y,1,1),date(2026,1,1),mutations)}
            if len(targets)==1 and targets.issubset(target):
                k=next(iter(targets))
                mapping[c]=k
                expected[k]=expected.get(k,0)+1
            else:
                blocked.update(targets.intersection(target))
        raw=raw[raw.name_ok].copy()
        raw["municipality_id"]=raw.code.map(mapping)
        present=0
        for mid,g in raw.dropna(subset=["municipality_id"]).groupby("municipality_id"):
            if mid in blocked:
                continue
            row=aggregate_group(g,expected[mid])
            if row is None:
                continue
            results.append({"municipality_id":mid,"year":y,
                            "available_from_proxy":f"{y+4}-01-01",**row})
            present+=1
        report.append({"year":y,"source_rows":len(read_source(path)),"snapshot_communes":len(s),
                       "name_code_matches":len(raw),"encoding_recovered":encoding_recovered,"usable_target_communes":present,
                       "split_targets_excluded":len(blocked),"snapshot":si,
                       "workbook_url":rec["url"],"workbook_sha256":rec["sha256"]})
        print("INCOME_YEAR",json.dumps(report[-1],ensure_ascii=False),flush=True)
    frame=pd.DataFrame(results)
    if frame.empty or frame.duplicated(["year","municipality_id"]).any() or frame.year.nunique()!=16:
        raise ValueError("Incomplete income dataset")
    frame["available_from_proxy"]=pd.to_datetime(frame.available_from_proxy)
    frame.to_parquet(output/"income_features.parquet",index=False)
    result={"status":"complete","strict_forecast_ready":False,"source_intro":INTRO,"mutations":prov,
            "availability":"reference year+4 Jan 1 proxy, current archive vintage not certified historically",
            "geography":"tax year Jan 1 to OFS 2026; territory exchanges excluded in register request; ambiguous split/partial mergers rejected",
            "rows":len(frame),"years":years,"municipalities":int(frame.municipality_id.nunique()),
            "missing":{c:float(frame[c].isna().mean()) for c in TAX_FEATURES},"year_audit":report,
            "income_sha256":digest(output/"income_features.parquet")}
    (output/"manifest.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print("ACQUISITION",json.dumps(result,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--geography",type=Path)
    a=p.parse_args()
    acquire(a.input,a.output,a.geography)


if __name__=="__main__":
    main()
