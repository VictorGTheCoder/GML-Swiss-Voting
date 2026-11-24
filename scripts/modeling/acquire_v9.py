"""V9 target-blind corpus audit and economic input acquisition.

Use only official source metadata and texts. Candidate brochure matches are
conservative retrospective research links, never strict-forecast admissions.
The STATENT source is a later vintage; two-year lag is a conservative
availability proxy, not evidence that the exact historical cells were published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from scripts.common.config import ROOT
from scripts.ofs_votes.parse_ofs_votes import data_cube, read_px
from scripts.repertoire_communes.commune_crosswalk import load_mutations, resolve

TEXT_ROOT = ROOT / "data/processed/federal_explanations"
STATENT_URL = "https://www.pxweb.bfs.admin.ch/DownloadFile.aspx?file=px-x-0602010000_102"
MUTATIONS_URL = "https://www.agvchapp.bfs.admin.ch/api/communes/mutations"
MODEL_ID = "intfloat/multilingual-e5-small"
# Pinned immutable revision from the model's published evaluation metadata.
MODEL_REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(s):
    s = unicodedata.normalize("NFKD", str(s).casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", s))


def title_score(a, b):
    a, b = norm(a), norm(b)
    if not a or not b or len(a) < 12 or len(b) < 12:
        return 0.
    if a == b:
        return 1.
    # Exact full phrase containment for headers with additional words.
    if (" "+a+" ") in (" "+b+" ") or (" "+b+" ") in (" "+a+" "):
        if min(len(a),len(b)) / max(len(a),len(b)) >= .65:
            return .97
    return SequenceMatcher(None,a,b,autojunk=False).ratio()


def choose_matches(roster, sections):
    """One-to-one mutual unique title matches within an already-linked source/date."""
    selected = []
    for _, group in roster.groupby(["vote_date","source_id"], dropna=False):
        source = group.source_id.iloc[0]
        if pd.isna(source):
            continue
        sub = sections[sections.source_id.eq(source)]
        if sub.empty:
            continue
        score = np.array([[max(title_score(s.title,r.titel_kurz_f),
                               title_score(s.title,r.titel_off_f))
                           for s in sub.itertuples()] for r in group.itertuples()])
        for i, row in enumerate(group.itertuples()):
            j = int(score[i].argmax())
            others = np.delete(score[i],j)
            competitors = np.delete(score[:,j],i)
            value = float(score[i,j])
            if value < .88 or (len(others) and value-float(others.max()) < .08):
                continue
            if len(competitors) and value-float(competitors.max()) < .08:
                continue
            s = sub.iloc[j]
            if str(s.pdf_sha256)!=str(row.pdf_sha256):
                continue
            selected.append({"vote_id":str(row.vote_id),"source_id":source,
                             "object_id":s.object_id,"title_similarity":value,
                             "section_title":s.title,"pdf_sha256":str(s.pdf_sha256)})
    return pd.DataFrame(selected,columns=["vote_id","source_id","object_id","title_similarity",
                                          "section_title","pdf_sha256"])


def source_text(output):
    # Read only title metadata, never the Swissvotes outcome columns.
    sv = pd.read_parquet(ROOT/"data/processed/swissvotes/swissvotes_clean.parquet",
                         columns=["vote_key","vote_date","titel_kurz_f","titel_off_f"])
    sv["vote_key"]=sv.vote_key.astype(str)
    modeled = pd.read_csv(ROOT/"data/processed/municipal_v3/object_features.csv",
                          dtype={"vote_id":str,"vote_key":str},usecols=["vote_id","vote_key","vote_date"])
    modeled["vote_date"]=pd.to_datetime(modeled.vote_date)
    modeled=modeled[modeled.vote_date.between("1990-01-01","2022-12-31")]
    sv["vote_date"]=pd.to_datetime(sv.vote_date)
    roster=modeled.merge(sv,on=["vote_key","vote_date"],validate="one_to_one",how="left")
    if roster.titel_off_f.isna().all() or len(roster)!=306 or roster.vote_id.duplicated().any():
        raise ValueError(f"Unexpected object roster {len(roster)}")
    obj=pd.read_parquet(TEXT_ROOT/"objects.parquet",
                        columns=["vote_id","vote_date","source_id","pdf_sha256","brochure_status","availability_status"])
    obj["vote_id"]=obj.vote_id.astype(str)
    obj["vote_date"]=pd.to_datetime(obj.vote_date)
    roster=roster.merge(obj,on=["vote_id","vote_date"],how="left",validate="one_to_one")
    sections=pd.read_parquet(TEXT_ROOT/"sections.parquet",
                            columns=["source_id","object_id","pdf_sha256","title","summary_official","full_text"])
    sources=pd.read_parquet(TEXT_ROOT/"sources.parquet",
                           columns=["source_id","pdf_sha256","vote_date","official_url","language"])
    sources["vote_date"]=pd.to_datetime(sources.vote_date)
    sources=sources[sources.language.eq("fr")&sources.official_url.str.match(r"^https://(?:www\.)?bk\.admin\.ch/",na=False)]
    if sources.source_id.duplicated().any():
        raise ValueError("Duplicate source identity")
    # Require same source, date and hash, plus an explicit candidate link.
    roster=roster.merge(sources[["source_id","pdf_sha256","vote_date","official_url"]],
                        on=["source_id","pdf_sha256","vote_date"],how="left",validate="many_to_one")
    eligible=roster[roster.official_url.notna()&roster.brochure_status.eq("FOUND")]
    matches=choose_matches(eligible,sections)
    links=pd.read_parquet(TEXT_ROOT/"section_links.parquet",columns=["vote_id","object_id","source_id","pdf_sha256"])
    links["vote_id"]=links.vote_id.astype(str)
    matches=matches.merge(links.drop_duplicates(),on=["vote_id","object_id","source_id","pdf_sha256"],
                          how="inner",validate="one_to_one")
    if matches.vote_id.duplicated().any() or matches.object_id.duplicated().any():
        raise ValueError("Ambiguous section match")
    # Only official summaries of reasonable length; don't concatenate entire
    # multi-object PDFs. Full-text is not automatically admitted.
    matches=matches.merge(sections[["object_id","summary_official"]],on="object_id",validate="one_to_one")
    matches["summary_official"]=matches.summary_official.fillna("").astype(str)
    matches["usable_summary"]=matches.summary_official.str.len().between(100,20000)
    text=roster[["vote_id","vote_date","titel_kurz_f","titel_off_f"]].copy()
    text["title_text"]=text.titel_off_f.fillna(text.titel_kurz_f).fillna("").astype(str)
    if text.title_text.str.len().lt(5).any():
        raise ValueError("Missing exact title")
    text=text.merge(matches[["vote_id","summary_official","usable_summary","pdf_sha256","title_similarity"]],
                    on="vote_id",how="left",validate="one_to_one")
    text["usable_summary"]=text.usable_summary.eq(True)
    text["document_text"]=text.title_text
    mask=text.usable_summary
    text.loc[mask,"document_text"]=text.loc[mask,"title_text"]+"\n"+text.loc[mask,"summary_official"]
    text=text.drop(columns=["summary_official"])
    text.to_parquet(output/"text_corpus.parquet",index=False)
    # Metadata inventory excludes complete brochure texts.
    matches.drop(columns=["summary_official"]).to_csv(output/"brochure_matches.csv",index=False)
    audit={"objects":len(text),"title_coverage":int(text.title_text.ne("").sum()),
           "candidate_matches":len(matches),"usable_summaries":int(mask.sum()),
           "evaluation_usable_summaries":int((mask&text.vote_date.ge("2016-01-01")).sum()),
           "strict_forecast_ready":False,"historical_version_verified":False,
           "source_sha256":{p.name:digest(p) for p in TEXT_ROOT.glob("*.parquet")}}
    print("TEXT_AUDIT",json.dumps(audit),flush=True)
    return text,audit


def embeddings(text,output):
    """Frozen multilingual E5, mean pooling over token chunks, normalized."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    torch.set_num_threads(2)
    tokenizer=AutoTokenizer.from_pretrained(MODEL_ID,revision=MODEL_REVISION,trust_remote_code=False)
    model=AutoModel.from_pretrained(MODEL_ID,revision=MODEL_REVISION,trust_remote_code=False,
                                    use_safetensors=True).eval()
    def encode(values):
        chunks=[]; owners=[]
        for i,value in enumerate(values):
            tokens=tokenizer("query: "+value,add_special_tokens=False,truncation=False)["input_ids"]
            for start in range(0,len(tokens),400):
                # Preserve prefix in every chunk rather than truncating summary.
                prefix=tokenizer("query: ",add_special_tokens=False)["input_ids"]
                chunk=tokens[start:start+400] if start==0 else prefix+tokens[start:start+400]
                chunks.append(tokenizer.prepare_for_model(chunk,add_special_tokens=True,return_attention_mask=True))
                owners.append(i)
        result=np.zeros((len(values),384),float)
        with torch.inference_mode():
            for start in range(0,len(chunks),16):
                batch=tokenizer.pad(chunks[start:start+16],return_tensors="pt")
                hidden=model(**batch).last_hidden_state
                mask=batch["attention_mask"].unsqueeze(-1)
                pooled=(hidden*mask).sum(dim=1)/mask.sum(dim=1).clamp(min=1)
                arr=torch.nn.functional.normalize(pooled,p=2,dim=1).cpu().numpy()
                np.add.at(result,owners[start:start+16],arr)
        result/=np.linalg.norm(result,axis=1,keepdims=True).clip(min=1e-12)
        return result
    title=encode(text.title_text.tolist())
    document=encode(text.document_text.tolist())
    np.savez_compressed(output/"embeddings.npz",vote_id=text.vote_id.astype(str).to_numpy(dtype=str),
                        title=title,document=document)
    return {"model":MODEL_ID,"revision":MODEL_REVISION,"dimension":384,"sha256":digest(output/"embeddings.npz")}


def download(url,path,params=None):
    response=requests.get(url,params=params,timeout=60,headers={"User-Agent":"GML-Swiss-Voting research"})
    response.raise_for_status()
    path.write_bytes(response.content)
    return {"url":response.url,"sha256":digest(path),"bytes":path.stat().st_size}


def map_counts(frame, mapping):
    """Aggregate counts before deriving shares. Unresolved splits stay missing."""
    frame=frame.copy()
    frame["municipality_id"]=frame.source_code.map(mapping)
    frame=frame[frame.municipality_id.notna()]
    counts=["jobs_total","jobs_primary","jobs_secondary","jobs_tertiary","establishments_total"]
    # Sum only if every component of a merger is known; do not treat X as zero.
    aggregated=frame.groupby(["year","municipality_id"])[counts].agg(
        lambda s: s.sum() if s.notna().all() else np.nan).reset_index()
    denominator=aggregated.jobs_total.where(aggregated.jobs_total>0)
    for sector in ("primary","secondary","tertiary"):
        aggregated["econ_share_"+sector]=aggregated["jobs_"+sector]/denominator
    aggregated["econ_log_jobs"]=np.log1p(aggregated.jobs_total)
    aggregated["econ_log_establishments"]=np.log1p(aggregated.establishments_total)
    aggregated["available_from_proxy"]=pd.to_datetime((aggregated.year+2).astype(str)+"-01-01")
    return aggregated


def economic_source(output):
    path=output/"statent.px"
    prov=download(STATENT_URL,path)
    px=read_px(path)
    m=px.metadata
    dims=m["STUB"]+m["HEADING"]
    print("STATENT_DIMENSIONS",json.dumps({d:{"count":len(m[f'CODES("{d}")']),
        "first_labels":m[f'VALUES("{d}")'][:12]} for d in dims},ensure_ascii=False),flush=True)
    # Validate source geography instead of inferring from a current snapshot.
    header=path.read_text(encoding="utf-8-sig").split("DATA=",1)[0]
    if "01.01.2024" not in header and "1.1.2024" not in header:
        raise ValueError("STATENT source geography differs from audited 2024 vintage")
    def dim(*terms):
        matches=[d for d in dims if any(term in norm(d) for term in terms)]
        if len(matches)!=1:
            raise ValueError(f"Ambiguous dimension {terms}: {matches}")
        return matches[0]
    year,place,sector,unit=dim("jahr","annee"),dim("gemeinde","commune"),dim("wirtschaftssektor","secteur economique"),dim("beobachtungseinheit","unite d observation")
    order=[year,place,sector,unit]
    if set(order)!=set(dims):
        raise ValueError("Unexpected STATENT dimensions")
    cube=np.transpose(data_cube(px,dims),[dims.index(d) for d in order])
    labels={d:m[f'VALUES("{d}")'] for d in order}
    codes={d:m[f'CODES("{d}")'] for d in order}
    def unique_index(d,patterns):
        hits=[i for i,s in enumerate(labels[d]) if any(re.fullmatch(pattern,norm(s)) for pattern in patterns)]
        if len(hits)!=1:
            raise ValueError(f"Cannot identify {d}: {patterns}, labels {labels[d]}")
        return hits[0]
    sectors={
      "total":unique_index(sector,[r"total",r"wirtschaftssektor total",r"secteur economique total",r"alle sektoren"]),
      "primary":unique_index(sector,[r"primarsektor",r"1 sektor",r"1 sektor primarsektor",r"secteur primaire",r"1 secteur.*"]),
      "secondary":unique_index(sector,[r"sekundarsektor",r"2 sektor",r"2 sektor sekundarsektor",r"secteur secondaire",r"2 secteur.*"]),
      "tertiary":unique_index(sector,[r"tertiarsektor",r"3 sektor",r"3 sektor tertiarsektor",r"secteur tertiaire",r"3 secteur.*"]),
    }
    jobs=unique_index(unit,[r"beschaftigte",r"beschaftigte total",r"emplois",r"emplois total"])
    est=unique_index(unit,[r"arbeitsstatten",r"arbeitsstatten total",r"etablissements",r"etablissements total"])
    records=[]
    for yi,y in enumerate(codes[year]):
        if not str(y).isdigit() or not 2011<=int(y)<=2020:
            continue
        for pi,c in enumerate(codes[place]):
            # Exclude aggregates, require numeric BFS IDs.
            if not re.fullmatch(r"\d{1,4}",str(c)):
                continue
            code=str(int(c))
            if int(code)<=0:
                continue
            row={"year":int(y),"source_code":code}
            row.update({"jobs_"+k:float(cube[yi,pi,j,jobs]) for k,j in sectors.items()})
            row["establishments_total"]=float(cube[yi,pi,sectors["total"],est])
            records.append(row)
    frame=pd.DataFrame(records)
    if frame.empty or frame.duplicated(["year","source_code"]).any() or frame.source_code.nunique()<2000:
        raise ValueError("Unexpected STATENT commune population")
    mutations_path=output/"mutations.csv"
    mp=download(MUTATIONS_URL,mutations_path,{"includeTerritoryExchange":"false","startPeriod":"01-01-2024","endPeriod":"01-01-2026","useBfsCode":"true"})
    mutations=load_mutations(mutations_path)
    typ=pd.read_parquet(ROOT/"data/processed/typologies/commune_typologies.parquet",columns=["municipality_id"])
    allowed=set(typ.municipality_id.astype(str))
    mapping={}
    unresolved=[]
    for c in frame.source_code.unique():
        targets=resolve(c,date(2024,1,1),date(2026,1,1),mutations)
        normalized={str(int(t)).zfill(4) for t in targets}
        if len(normalized)==1 and normalized.issubset(allowed):
            mapping[c]=next(iter(normalized))
        else:
            unresolved.append({"source":c,"targets":sorted(normalized)})
    if len(mapping)<.98*frame.source_code.nunique():
        raise ValueError(f"Excess unresolved municipalities: {unresolved[:20]}")
    result=map_counts(frame,mapping)
    result.to_parquet(output/"economic_features.parquet",index=False)
    return {"statent":prov,"mutations":mp,"source_geography":"2024-01-01","target_geography":"2026-01-01",
            "year_range":[int(result.year.min()),int(result.year.max())],"rows":len(result),
            "municipalities":int(result.municipality_id.nunique()),"unresolved":unresolved,
            "missingness":{c:float(result[c].isna().mean()) for c in result if c.startswith("econ_")},
            "sha256":digest(output/"economic_features.parquet"),"availability":"year + 2 Jan 1 proxy; historical vintage unverified"}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--skip-neural",action="store_true")
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    text,audit=source_text(a.output)
    result={"status":"complete_with_explicit_gates","text":audit,"strict_forecast_ready":False}
    if not a.skip_neural:
        try:
            result["embedding"]=embeddings(text,a.output)
        except Exception as exc:
            result["embedding"]={"status":"blocked","reason":str(exc)[:1000]}
    else:
        result["embedding"]={"status":"skipped"}
    try:
        result["economy"]=economic_source(a.output)
    except Exception as exc:
        result["economy"]={"status":"blocked","reason":str(exc)[:1000]}
    result["text_corpus_sha256"]=digest(a.output/"text_corpus.parquet")
    (a.output/"manifest.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("ACQUISITION",json.dumps(result,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
