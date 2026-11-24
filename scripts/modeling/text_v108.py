"""V10.8: reconstruct safe page-level brochure candidates and literal policy cues.

Do not trust the legacy section title/body alignment. Match each original
page to a unique object on the same official brochure date/hash. Candidates
remain retrospective; no historical publication certification is invented.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.acquire_v9 import TEXT_ROOT, digest, embeddings, norm

CUES = {
    "ban": r"\b(interdi\w*|prohib\w*)\b",
    "abolish": r"\b(supprim\w*|suppression\w*|abrog\w*|abol\w*)\b",
    "raise": r"\b(augment\w*|relev\w*|hausse\w*)\b",
    "reduce": r"\b(redui\w*|reduc\w*|abaiss\w*|dimin\w*|baiss\w*)\b",
    "funding": r"\b(financ\w*|subvention\w*|contribut\w*)\b",
    "tax": r"\b(impot\w*|taxe\w*|fisc\w*|tva)\b",
    "regulation": r"\b(reglement\w*|autorisation\w*|oblig\w*|norme\w*)\b",
    "benefit": r"\b(rente\w*|allocation\w*|prestation\w*|assurance\w*)\b",
    "institution": r"\b(competence\w*|constitution\w*|parlement\w*|canton\w*)\b",
    "infrastructure": r"\b(construction\w*|route\w*|tunnel\w*|logement\w*)\b",
}
STOP = set("le la les l de d du des un une et ou sur pour par au aux a en loi federal federale arrete modification initiative populaire relative concernant contre projet texte vote".split())


def clean_text(value):
    text = str(value).replace("\u00ad", "").replace("\x00", "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    return re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)


def title_match(title, header):
    a, b = norm(clean_text(title)), norm(clean_text(header))
    if len(a) < 12:
        return 0.
    if f" {a} " in f" {b} ":
        return 1.
    words = {w for w in a.split() if len(w) >= 3 and w not in STOP}
    if len(words) < 3:
        return 0.
    ratio = len(words.intersection(b.split())) / len(words)
    return .94 if ratio == 1. else 0.


def page_candidates(pages, titles):
    """No inferred order mapping. Require a unique strong title/question match."""
    result = []
    for page in pages:
        number = int(page["page_number"])
        if number < 2:
            continue
        text = clean_text(page["text"])
        if not 180 <= len(text) <= 14000:
            continue
        heading = text[:1200]
        head = norm(heading)
        if not ("en bref" in head or "la question a laquelle" in head
                or "acceptez vous" in head or "l essentiel en bref" in head):
            continue
        # Most modern briefs are first pages; later question pages are allowed
        # only with an explicit question, not a repeated contents title.
        if number > 3 + 2 * len(titles) and "acceptez vous" not in head and "la question a laquelle" not in head:
            continue
        hits = [(vote, max(title_match(t, heading) for t in aliases))
                for vote, aliases in titles.items()]
        hits = sorted((v, s) for v, s in hits if s >= .94)
        if len(hits) != 1:
            continue
        vote, confidence = hits[0]
        result.append({"vote_id": vote, "page": number, "score": confidence,
                       "text": text, "method": str(page.get("method", ""))})
    return result


def pick_pages(pages, titles):
    matches = page_candidates(pages, titles)
    out = {}
    for vote in titles:
        found = [r for r in matches if r["vote_id"] == vote]
        if not found:
            continue
        # Only the first independently matched page. No adjacent page is
        # included by positional guess. Prefer exact over token evidence.
        chosen = sorted(found, key=lambda r: (-r["score"], r["page"]))[0]
        out[vote] = chosen
    return out


def cues(text):
    plain = norm(text)
    return {name: int(bool(re.search(pattern, plain))) for name, pattern in CUES.items()}


def source_corpus(output):
    sv = pd.read_parquet(ROOT/"data/processed/swissvotes/swissvotes_clean.parquet",
                         columns=["vote_key","vote_date","titel_kurz_f","titel_off_f"])
    sv["vote_key"] = sv.vote_key.astype(str)
    sv["vote_date"] = pd.to_datetime(sv.vote_date)
    roster = pd.read_csv(ROOT/"data/processed/municipal_v3/object_features.csv",
                         usecols=["vote_id","vote_key","vote_date"],dtype={"vote_id":str,"vote_key":str})
    roster["vote_date"] = pd.to_datetime(roster.vote_date)
    roster = roster[roster.vote_date.between("1990-01-01","2022-12-31")].merge(
        sv,on=["vote_key","vote_date"],validate="one_to_one")
    if len(roster) != 306 or roster.vote_id.duplicated().any():
        raise ValueError("Unexpected corpus roster")
    src = pd.read_parquet(TEXT_ROOT/"sources.parquet",columns=["source_id","pdf_sha256","vote_date","official_url","language"])
    src["vote_date"] = pd.to_datetime(src.vote_date)
    src = src[src.language.eq("fr") & src.official_url.str.match(r"^https://(?:www\.)?bk\.admin\.ch/",na=False)]
    src = src[src.vote_date.between("1990-01-01","2022-12-31")]
    pages = pd.read_parquet(TEXT_ROOT/"pages.parquet",columns=["source_id","pdf_sha256","page_number","text","method","status"])
    objects = pd.read_parquet(TEXT_ROOT/"objects.parquet",columns=["vote_id","vote_date","source_id","pdf_sha256"])
    objects["vote_id"] = objects.vote_id.astype(str)
    objects["vote_date"] = pd.to_datetime(objects.vote_date)
    roster = roster.merge(objects,on=["vote_id","vote_date"],how="left",validate="one_to_one")
    result, audit = [], []
    for day, group in roster.groupby("vote_date"):
        approved = {}
        day_sources = src[src.vote_date.eq(day)]
        if len(day_sources) == 1:
            s = day_sources.iloc[0]
            eligible = group[group.source_id.eq(s.source_id) & group.pdf_sha256.eq(s.pdf_sha256)]
            # Compare against ALL same-day titles to avoid accidental cross-object admission.
            titles = {str(r.vote_id): [str(x) for x in (r.titel_off_f,r.titel_kurz_f) if pd.notna(x)]
                      for r in group.itertuples()}
            p = pages[pages.source_id.eq(s.source_id) & pages.pdf_sha256.eq(s.pdf_sha256) & pages.text.notna()]
            if p.page_number.duplicated().any():
                raise ValueError("Ambiguous page numbers")
            picked = pick_pages(p.to_dict("records"), titles)
            approved = {v: x for v,x in picked.items() if v in set(eligible.vote_id)}
        for r in group.itertuples():
            title = str(r.titel_off_f if pd.notna(r.titel_off_f) else r.titel_kurz_f)
            x = approved.get(r.vote_id)
            page_text = x["text"] if x else ""
            row = {"vote_id":r.vote_id,"vote_date":day,"title_text":title,
                   "document_text":title+"\n"+page_text if x else title,"usable_summary":bool(x)}
            row.update({"title_cue_"+k:v for k,v in cues(title).items()})
            row.update({"page_cue_"+k:v for k,v in cues(page_text).items()})
            result.append(row)
            if x:
                audit.append({"vote_id":r.vote_id,"vote_date":str(day.date()),"source_id":r.source_id,
                              "pdf_sha256":r.pdf_sha256,"source_url":str(day_sources.iloc[0].official_url),
                              "page":x["page"],"score":x["score"],"method":x["method"],
                              "header":x["text"][:350], "literal_cues":json.dumps(cues(page_text))})
    corpus = pd.DataFrame(result).sort_values("vote_id")
    corpus.to_parquet(output/"text_corpus.parquet",index=False)
    pd.DataFrame(audit).to_csv(output/"page_matches.csv",index=False)
    counts = {"objects":len(corpus),"matched_pages":int(corpus.usable_summary.sum()),
              "validation_matches":int((corpus.usable_summary & corpus.vote_date.ge("2016-01-01")).sum()),
              "matching_policy":"unique title/question page, source identity and hash; retrospective candidate, not strict temporal certification"}
    print("TEXT_AUDIT",json.dumps(counts),flush=True)
    return corpus,counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    corpus,counts=source_corpus(a.output)
    em=embeddings(corpus,a.output)
    result={"status":"complete","strict_forecast_ready":False,"text":counts,
            "embedding":em,"text_corpus_sha256":digest(a.output/"text_corpus.parquet"),
            "matches_sha256":digest(a.output/"page_matches.csv"),
            "source_sha256":{p.name:digest(p) for p in TEXT_ROOT.glob("*.parquet")}}
    (a.output/"manifest.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print("ACQUISITION",json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
