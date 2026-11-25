"""V12.2b: target-blind diagnosis of missing object-to-brochure page links."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.modeling.acquire_v9 import TEXT_ROOT, norm
from scripts.modeling.documentary_audit_v112 import (
    MARKERS,
    audited_documents,
    exact_hit,
    independent_pages,
)
from scripts.modeling.semantic_poll_comparison_v4 import sha
from scripts.modeling.text_v108 import clean_text


def page_diagnostics(pages, titles, vote):
    """Return hash-only leads, not accepted matches or training text."""
    strict = dict(independent_pages(pages, titles)[vote])
    leads = []
    for page in pages:
        number = int(page["page_number"])
        if number < 2 or pd.isna(page["text"]):
            continue
        content = clean_text(page["text"])
        if not 180 <= len(content) <= 14000:
            continue
        heading = content[:1200]
        if not exact_hit(titles[vote], heading):
            continue
        others = [key for key, aliases in titles.items()
                  if key != vote and exact_hit(aliases, content)]
        marker = any(m in norm(heading) for m in MARKERS)
        if number in strict:
            kind = "strict_candidate"
        elif others:
            kind = "other_object_title"
        elif not marker:
            kind = "no_summary_marker"
        else:
            kind = "other_rejection"
        leads.append({"page": number, "kind": kind, "other_ids": sorted(others),
                      "sha256": hashlib.sha256(content.encode()).hexdigest()})
    return sorted(leads, key=lambda row: row["page"])


def run(acquisition, output):
    manifest = json.loads((acquisition / "manifest.json").read_text())
    path = acquisition / "text_corpus.parquet"
    if manifest["status"] != "complete" or sha(path) != manifest["text_corpus_sha256"]:
        raise ValueError("Frozen text corpus changed")
    corpus = pd.read_parquet(path).set_index("vote_id", verify_integrity=True)
    corpus.index = corpus.index.astype(str)
    corpus["vote_date"] = pd.to_datetime(corpus.vote_date)
    if len(corpus) != 306 or corpus.vote_date.ge("2023-01-01").any():
        raise ValueError("Unexpected text population")
    audit, _ = audited_documents(corpus, manifest)
    dev = audit[audit.vote_date.ge("2016-01-01")]
    if len(dev) != 66 or dev.vote_date.nunique() != 23:
        raise ValueError("Development roster changed")
    gaps = dev[dev.exact_text.eq("")]
    if len(gaps) != 25:
        raise ValueError("Original gap count changed")
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
    objects = objects.set_index("vote_id", verify_integrity=True)
    pages = pd.read_parquet(TEXT_ROOT / "pages.parquet", columns=[
        "source_id", "pdf_sha256", "page_number", "text",
    ])
    results = []
    for day, group in gaps.groupby("vote_date"):
        all_day = dev[dev.vote_date.eq(day)]
        titles = {vote: [row.title_text] for vote, row in all_day.iterrows()}
        ds = sources[sources.vote_date.eq(day)]
        for vote in group.index:
            record = {"vote_id": vote, "vote_date": str(day.date()),
                      "same_day_exact_elsewhere": bool(all_day.exact_text.ne("").any()),
                      "source_count": len(ds), "leads": []}
            if len(ds) == 1:
                source = ds.iloc[0]
                linked = vote in objects.index and (
                    objects.loc[vote, "vote_date"] == day
                    and objects.loc[vote, "source_id"] == source.source_id
                    and objects.loc[vote, "pdf_sha256"] == source.pdf_sha256
                )
                pp = pages[pages.source_id.eq(source.source_id)
                           & pages.pdf_sha256.eq(source.pdf_sha256)]
                if pp.page_number.duplicated().any():
                    raise ValueError("Duplicate physical page")
                record.update(source_id=str(source.source_id), pdf_sha256=str(source.pdf_sha256),
                              source_url=source.official_url, link_matches=bool(linked),
                              leads=page_diagnostics(pp.to_dict("records"), titles, vote))
            results.append(record)
    report = {"status": "audit_only_not_admitted", "training_rows": 0,
              "strict_forecast_ready": False, "gaps": results,
              "same_day_exact_elsewhere": sum(r["same_day_exact_elsewhere"] for r in results),
              "strict_candidate_objects": sum(any(p["kind"] == "strict_candidate"
                                                   for p in r["leads"]) for r in results),
              "source_sha256": manifest["source_sha256"]}
    if output.exists():
        raise FileExistsError("Preserve earlier audit")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.acquisition, args.output)


if __name__ == "__main__":
    main()
