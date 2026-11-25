"""V12.2c: validate visually transcribed TOC leads against pinned text; no admission."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.modeling.acquire_v9 import TEXT_ROOT, norm
from scripts.modeling.semantic_poll_comparison_v4 import sha
from scripts.modeling.text_v108 import clean_text


def matches(text, alternatives):
    words = set(norm(clean_text(text)).split())
    return any(set(terms) <= words for terms in alternatives)


def review_entry(entry, titles, pages):
    """Identity and physical-page checks only, never a training admission."""
    hits = [vote for vote, title in titles.items() if matches(title, entry["terms"])]
    lo, hi = entry["summary"]
    if not 2 <= lo <= hi < entry["detail"] <= entry["arguments"] <= entry["legal"]:
        raise ValueError("Invalid TOC boundaries")
    numbers = list(range(lo, hi + 1))
    result = {"vote_ids": hits, "summary_pages": numbers, "shared": entry.get("shared"),
              "status": "unresolved_title", "page_hashes": []}
    if len(hits) != 1:
        return result
    if any(n not in pages or not isinstance(pages[n], str) for n in numbers):
        result["status"] = "missing_page"
        return result
    texts = [clean_text(pages[n]) for n in numbers]
    result["page_hashes"] = [
        {"page": n, "sha256": hashlib.sha256(t.encode()).hexdigest(), "chars": len(t)}
        for n, t in zip(numbers, texts, strict=True)
    ]
    if any(not 180 <= len(t) <= 14000 for t in texts):
        result["status"] = "page_length_rejected"
    elif not matches(" ".join(texts), entry["terms"]):
        result["status"] = "page_identity_unresolved"
    else:
        result["status"] = "shared_candidate" if entry.get("shared") else "unique_candidate"
    return result


def run(acquisition, gaps_path, toc_path, output):
    gaps = json.loads(gaps_path.read_text(encoding="utf-8"))
    toc = json.loads(toc_path.read_text(encoding="utf-8"))
    manifest = json.loads((acquisition / "manifest.json").read_text())
    if manifest["status"] != "complete" or manifest["source_sha256"] != gaps["source_sha256"]:
        raise ValueError("Unexpected source manifest")
    for name, digest in manifest["source_sha256"].items():
        if sha(TEXT_ROOT / name) != digest:
            raise ValueError("Source snapshot changed")
    corpus_path = acquisition / "text_corpus.parquet"
    if sha(corpus_path) != manifest["text_corpus_sha256"]:
        raise ValueError("Text corpus changed")
    corpus = pd.read_parquet(corpus_path, columns=["vote_id", "vote_date", "title_text"])
    corpus["vote_id"] = corpus.vote_id.astype(str)
    corpus["vote_date"] = pd.to_datetime(corpus.vote_date)
    if len(corpus) != 306 or corpus.vote_date.ge("2023-01-01").any():
        raise ValueError("Unexpected historical population")
    if corpus.vote_id.duplicated().any():
        raise ValueError("Duplicate vote")
    dev = corpus[corpus.vote_date.ge("2016-01-01")]
    if len(dev) != 66 or dev.vote_date.nunique() != 23:
        raise ValueError("Development roster changed")
    pages = pd.read_parquet(TEXT_ROOT / "pages.parquet",
                            columns=["source_id", "pdf_sha256", "page_number", "text"])
    records = []
    for date in toc["dates"]:
        day = pd.Timestamp(date["date"])
        titles = dev[dev.vote_date.eq(day)].set_index("vote_id").title_text.to_dict()
        expected = {g["vote_id"] for g in gaps["gaps"] if g["vote_date"] == date["date"]
                    and g["source_id"] == date["source_id"]
                    and g["pdf_sha256"] == date["pdf_sha256"] and g["link_matches"]}
        if expected != set(date["gap_ids"]) or not expected <= set(titles):
            raise ValueError("Gap or source identity changed")
        pp = pages[pages.source_id.eq(date["source_id"]) & pages.pdf_sha256.eq(date["pdf_sha256"])]
        if pp.page_number.duplicated().any():
            raise ValueError("Duplicate physical page")
        page_map = {int(p.page_number): p.text for p in pp.itertuples()}
        reviewed = [review_entry(entry, titles, page_map) for entry in date["entries"]]
        for record in reviewed:
            record.update(date=date["date"], source_id=date["source_id"],
                          gap_ids=sorted(expected.intersection(record["vote_ids"])))
        for i, first in enumerate(reviewed):
            for second in reviewed[i + 1:]:
                overlap = set(first["summary_pages"]) & set(second["summary_pages"])
                shared = first["shared"] and first["shared"] == second["shared"]
                if overlap and not shared:
                    raise ValueError("Unexpected overlapping TOC ranges")
                if set(first["vote_ids"]) & set(second["vote_ids"]):
                    first["status"] = second["status"] = "ambiguous_multiple_entries"
        records.extend(reviewed)
    report = {"status": "audit_only_not_admitted", "training_rows": 0,
              "strict_forecast_ready": False, "records": records,
              "source_sha256": manifest["source_sha256"]}
    if output.exists():
        raise FileExistsError("Preserve earlier audit")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
    output.write_text(payload, encoding="utf-8")
    print(payload, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition", type=Path, required=True)
    parser.add_argument("--gaps", type=Path, required=True)
    parser.add_argument("--toc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.acquisition, args.gaps, args.toc, args.output)


if __name__ == "__main__":
    main()
