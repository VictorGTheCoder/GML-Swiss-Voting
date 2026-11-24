"""Target-blind documentary audit with exact title and source identity.

No positional inference of a section, no vote results, no inferred individual
preferences. Independently matched pages are retrospective candidates only.
"""
from __future__ import annotations

import hashlib
import re

import pandas as pd

from scripts.modeling.acquire_v9 import TEXT_ROOT, norm
from scripts.modeling.semantic_poll_comparison_v4 import sha
from scripts.modeling.text_v108 import CUES, clean_text

MARKERS = ("en bref", "la question a laquelle", "acceptez vous", "l essentiel en bref",
           "en detail", "le projet en detail")
QUESTION = re.compile(r"\b(?:acceptez[-\s]+vous|voulez[-\s]+vous|approuvez[-\s]+vous)\b[^?]{10,700}\?", re.I)


def exact_hit(aliases, text):
    normalized = " " + norm(text) + " "
    return any(len(a) >= 12 and f" {a} " in normalized
               for a in (norm(clean_text(t)) for t in aliases))


def independent_pages(pages, titles):
    result = {v: [] for v in titles}
    for page in pages:
        if pd.isna(page["text"]) or int(page["page_number"]) < 2:
            continue
        text = clean_text(page["text"])
        if not 180 <= len(text) <= 14000:
            continue
        heading = text[:1200]
        if not any(m in norm(heading) for m in MARKERS):
            continue
        hits = [v for v, aliases in titles.items() if exact_hit(aliases, heading)]
        if len(hits) != 1:
            continue
        vote = hits[0]
        # Exclude a page containing another object's explicit title anywhere.
        if any(v != vote and exact_hit(aliases, text) for v, aliases in titles.items()):
            continue
        result[vote].append((int(page["page_number"]), text))
    return {v: sorted(rows) for v, rows in result.items()}


def question_text(text):
    normalized = " ".join(text.split())
    return " ".join(dict.fromkeys(m.group() for m in QUESTION.finditer(normalized)))


def mechanism_text(text):
    # Literal contextual sentences, not a stance or inferred policy direction.
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    found = [s for s in sentences if 25 <= len(s) <= 700
             and any(re.search(pattern, norm(s)) for pattern in CUES.values())]
    return " ".join(dict.fromkeys(found))


def audited_documents(corpus, manifest):
    for name, digest in manifest["source_sha256"].items():
        if sha(TEXT_ROOT / name) != digest:
            raise ValueError("Historical text source changed: " + name)
    sources = pd.read_parquet(TEXT_ROOT / "sources.parquet", columns=[
        "source_id", "pdf_sha256", "vote_date", "official_url", "language",
    ])
    sources["vote_date"] = pd.to_datetime(sources.vote_date)
    sources = sources[sources.language.eq("fr") & sources.official_url.str.match(
        r"^https://(?:www\.)?bk\.admin\.ch/", na=False)]
    sources = sources[sources.vote_date.between("1990-01-01", "2022-12-31")]
    objects = pd.read_parquet(TEXT_ROOT / "objects.parquet", columns=[
        "vote_id", "vote_date", "source_id", "pdf_sha256",
    ])
    objects["vote_date"] = pd.to_datetime(objects.vote_date)
    objects["vote_id"] = objects.vote_id.astype(str)
    objects = objects[objects.vote_date.between("1990-01-01", "2022-12-31")]
    if objects.vote_id.duplicated().any():
        raise ValueError("Ambiguous object-to-source link")
    pages = pd.read_parquet(TEXT_ROOT / "pages.parquet", columns=[
        "source_id", "pdf_sha256", "page_number", "text",
    ])
    linked = corpus.reset_index().merge(objects, on=["vote_id", "vote_date"], how="left",
                                        validate="one_to_one")
    records, audit = [], []
    for day, group in linked.groupby("vote_date"):
        titles = {r.vote_id: [r.title_text] for r in group.itertuples()}
        day_sources = sources[sources.vote_date.eq(day)]
        candidates = {}
        if len(day_sources) == 1:
            source = day_sources.iloc[0]
            eligible = set(group.loc[group.source_id.eq(source.source_id)
                                     & group.pdf_sha256.eq(source.pdf_sha256), "vote_id"])
            pp = pages[pages.source_id.eq(source.source_id) & pages.pdf_sha256.eq(source.pdf_sha256)]
            if pp.page_number.duplicated().any():
                raise ValueError("Duplicate physical page")
            candidates = {v: rows for v, rows in independent_pages(pp.to_dict("records"), titles).items()
                          if v in eligible}
        for row in group.itertuples():
            matched = candidates.get(row.vote_id, [])
            first = matched[0][1] if matched else ""
            multi = "\n".join(t for _, t in matched)
            question = question_text(multi)
            mechanism = mechanism_text(multi)
            record = {"vote_id": row.vote_id, "vote_date": day, "title_text": row.title_text,
                      "original_text": row.document_text, "original_covered": bool(row.usable_summary),
                      "exact_text": first, "multi_text": multi, "question_text": question,
                      "mechanism_text": mechanism}
            records.append(record)
            for number, text in matched:
                audit.append({"vote_id": row.vote_id, "vote_date": day, "source_id": row.source_id,
                              "pdf_sha256": row.pdf_sha256, "source_url": source.official_url,
                              "page": number, "page_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                              "question_found": bool(question_text(text)),
                              "mechanism_found": bool(mechanism_text(text))})
    result = pd.DataFrame(records).set_index("vote_id", verify_integrity=True)
    if set(result.index) != set(corpus.index):
        raise ValueError("Audit changed object roster")
    return result, pd.DataFrame(audit)


def variant_corpus(audit, field):
    result = audit[["title_text", "vote_date"]].copy()
    if field == "original_text":
        result["document_text"] = audit[field]
        result["usable_summary"] = audit.original_covered
    else:
        result["usable_summary"] = audit[field].str.len().gt(0)
        result["document_text"] = result.title_text + audit[field].map(lambda x: "\n" + x if x else "")
    return result
