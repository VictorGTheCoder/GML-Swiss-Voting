"""Replay cached Swissvotes and Chancellerie inputs against OFS vote coverage."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
from pathlib import Path

import pandas as pd

try:  # Support both `python scripts/...py` and package imports in tests.
    from .federal_explanations_layouts import extract_objects
    from .federal_explanations_ocr import extract_pdf_pages
    from .federal_explanations_swissvotes import join_swissvotes
    from .federal_explanations_temporal import apply_temporal_decision, filter_model_eligible
    from .federal_explanations_corrections import replay_corrections
    from .federal_explanations import _section_fields
    from .federal_explanations_relations import _recommendation, build_related_vote_data
except ImportError:
    from federal_explanations_layouts import extract_objects
    from federal_explanations_ocr import extract_pdf_pages
    from federal_explanations_swissvotes import join_swissvotes
    from federal_explanations_temporal import apply_temporal_decision, filter_model_eligible
    from federal_explanations_corrections import replay_corrections
    from federal_explanations import _section_fields
    from federal_explanations_relations import _recommendation, build_related_vote_data


def _list_value(value: object) -> list[str]:
    """Decode an explicitly supplied list field without inferring relations."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "null", "[]"}:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        parsed = [item.strip() for item in text.split(";") if item.strip()]
    return [str(item) for item in parsed] if isinstance(parsed, (list, tuple, set)) else [text]


def _official_fields(section: dict, vote_rows: list[dict]) -> dict:
    """Extract labeled summary/recommendations and annotate unresolved values."""
    full_text = "\n".join(passage["text"] for passage in section["passages"])
    try:
        parsed = _section_fields([f"Objet {section['order']}: {section['title']}\n{full_text}"])
    except ValueError:  # Legacy layouts do not use the modern object heading.
        parsed = {"summary_official": "", "council_recommendation_raw": "",
                  "parliament_recommendation_raw": ""}

    def labeled_value(label: str) -> str:
        aliases = {
            "Résumé officiel": r"Résumé officiel|Resume officiel|Résumé|Resume",
            "Conseil fédéral": r"Conseil fédéral|Conseil federal",
            "Parlement": r"Parlement",
        }
        pattern = aliases[label]
        boundary = r"(?=^(?:Résumé officiel|Resume officiel|Résumé|Resume|Texte complet|Conseil fédéral|Conseil federal|Parlement)\s*:|\Z)"
        found = re.search(rf"(?ims)^(?:{pattern})\s*:\s*(.*?){boundary}", full_text)
        return " ".join((found.group(1) or "").split()) if found else ""

    for field, label in (("summary_official", "Résumé officiel"),
                         ("council_recommendation_raw", "Conseil fédéral"),
                         ("parliament_recommendation_raw", "Parlement")):
        if not parsed.get(field):
            parsed[field] = labeled_value(label)

    if not parsed.get("summary_official"):
        lines = full_text.splitlines()
        start = next((i for i, line in enumerate(lines)
                      if re.match(r"(?i)^\s*(?:L’essentiel en bref|L'essentiel en bref|En bref)\s*$", line)), None)
        if start is not None:
            end = next((i for i in range(start + 1, len(lines))
                        if re.match(r"(?i)^\s*(?:Le projet en détail|Le texte en détail|En détail)\s*$", lines[i])), len(lines))
            parsed["summary_official"] = " ".join(" ".join(lines[start + 1:end]).split())

    joined_text = re.sub(r"-\s*\n\s*", "", full_text)
    joined_text = " ".join(joined_text.split())
    if not parsed.get("council_recommendation_raw") and not parsed.get("parliament_recommendation_raw"):
        recommendation = re.search(
            r"((?:Le Conseil fédéral et le Parlement|Le Conseil fédéral|Le Parlement)\s+"
            r"vous recommand(?:e|ent)\b.{0,250}?[.!])", joined_text, re.IGNORECASE
        )
        if recommendation:
            raw = recommendation.group(1).strip()
            if re.search(r"(?i)conseil fédéral.*parlement", raw):
                parsed["council_recommendation_raw"] = raw
                parsed["parliament_recommendation_raw"] = raw
            elif re.search(r"(?i)conseil fédéral", raw):
                parsed["council_recommendation_raw"] = raw
            else:
                parsed["parliament_recommendation_raw"] = raw
    summary = parsed["summary_official"] or None
    council_raw = parsed["council_recommendation_raw"] or None
    parliament_raw = parsed["parliament_recommendation_raw"] or None
    joint = council_raw and re.search(r"(?i)conseil fédéral et le parlement", council_raw)
    if joint and not parliament_raw:
        parliament_raw = council_raw
    context = vote_rows[0] if len(vote_rows) == 1 else {"related_vote_ids": []}
    result = {
        "summary_official": summary,
        "summary_missing_reason": None if summary else "official summary label not extracted or absent",
        "council_recommendation_raw": council_raw,
        "parliament_recommendation_raw": parliament_raw,
        "object_type": None,
        "object_type_reason": "object type not identifiable from extracted title",
    }
    for label, raw in (("council", council_raw), ("parliament", parliament_raw)):
        target, reason = _recommendation(raw, context)
        result[f"{label}_recommendation_target"] = target
        result[f"{label}_recommendation_reason"] = reason
        result[f"{label}_recommendation_position"] = (
            target.split("_", 1)[0] if target else None
        )
        result[f"{label}_recommendation_type"] = (
            target.split("_", 1)[1] if target and "_" in target else None
        )
    title = (section["title"] + "\n" + full_text).casefold()
    known_types = [("INITIATIVE", r"\binitiative\b"),
                   ("COUNTERPROPOSAL", r"contre[- ]projet"),
                   ("REFERENDUM", r"\bréférendum\b|\breferendum\b"),
                   ("LAW", r"\bloi fédérale\b|\bloi\b"),
                   ("DECREE", r"\barrêté fédéral\b|\barrete federal\b")]
    types = [name for name, pattern in known_types if re.search(pattern, title)]
    if len(types) == 1:
        result["object_type"] = types[0]
        result["object_type_reason"] = "identified from explicit title wording"
    elif len(types) > 1:
        result["object_type_reason"] = "ambiguous title contains multiple recognized object types"
    return result


def run_audit(ofs_path: Path, swissvotes_path: Path, sources_path: Path, output: Path,
              *, source_version: str, source_license: str = "CC BY 4.0") -> None:
    ofs_frame = pd.read_parquet(ofs_path) if ofs_path.suffix == ".parquet" else pd.read_csv(ofs_path, dtype={"vote_id": "string"})
    needed = {"vote_id", "vote_date", "is_tiebreak_question"}
    if not needed.issubset(ofs_frame.columns):
        raise ValueError(f"OFS input missing columns: {', '.join(sorted(needed - set(ofs_frame.columns)))}")
    expected = ofs_frame.drop_duplicates("vote_id").copy()
    expected["vote_id"] = expected.vote_id.astype(str)
    expected["vote_date"] = pd.to_datetime(expected.vote_date).dt.strftime("%Y-%m-%d")
    expected = expected[expected.vote_date.between("2011-01-01", "2026-12-31")]
    swiss = pd.read_csv(swissvotes_path, sep=None, engine="python", encoding="utf-8-sig", dtype=str, keep_default_na=False).to_dict("records")
    swiss_hash = hashlib.sha256(swissvotes_path.read_bytes()).hexdigest()
    joined = join_swissvotes(expected.to_dict("records"), swiss, source_version=source_version,
                             source_sha256=swiss_hash, license=source_license)
    manifest = json.loads(sources_path.read_text(encoding="utf-8"))
    documents = manifest.get("documents", [])
    output.mkdir(parents=True, exist_ok=True)
    originals = output / "originals"
    originals.mkdir(exist_ok=True)
    source_rows, page_rows, section_rows, correction_audit = [], [], [], []
    for doc in documents:
        path = Path(doc["pdf_path"])
        if not path.is_file():
            source_rows.append({**doc, "extraction_status": "MISSING_FILE", "pdf_sha256": None})
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        preserved = originals / f"{digest}.pdf"
        if not preserved.exists():
            shutil.copyfile(path, preserved)
        pages = extract_pdf_pages(path)
        page_rows.extend({"source_id": doc.get("source_id"), "pdf_sha256": digest, **row} for row in pages)
        structure = extract_objects([str(page["text"]) for page in pages], source_id=str(doc.get("source_id", "source")), source_sha256=digest)
        decision = doc.get("temporal_decision") or {"status": "INVESTIGATE", "source_sha256": ""}
        temporal = apply_temporal_decision(decision, digest)
        replayed = replay_corrections(digest, manifest.get("corrections", []))
        correction_audit.extend(replayed["issues"])
        for section in structure["objects"]:
            for (object_id, field), value in replayed["applied"].items():
                if object_id == section["object_id"] and field in {"title", "text"}:
                    section[field] = value
            refs = doc.get("ofs_vote_ids", [doc.get("ofs_vote_id", "")])
            if isinstance(refs, str):
                refs = [refs]
            linked_votes = [row for row in expected.to_dict("records") if str(row["vote_id"]) in {str(v) for v in refs}]
            section_rows.append({"source_id": doc.get("source_id"), "pdf_sha256": digest,
                                 "object_id": section["object_id"], "section_order": section["order"],
                                 "title": section["title"], "source_pages": section["source_pages"],
                                 "layout": section["layout"], "structure_status": structure["structure_status"],
                                 "full_text": "\n".join(p["text"] for p in section["passages"]),
                                 **_official_fields(section, linked_votes),
                                 "semantic_status": doc.get("semantic_status", "NOT_VALIDATED"),
                                 "correction_status": "APPLIED" if replayed["applied"] else "NONE"})
        source_rows.append({**doc, "pdf_sha256": digest, "extraction_status": "EXTRACTED",
                            "availability_status": temporal["status"],
                            "decision_source_sha256": temporal.get("source_sha256"),
                            "temporal_decision_stale": temporal.get("decision_stale", False),
                            "native_pages": sum(p["method"] == "native" for p in pages),
                            "ocr_pages": sum(p["method"] == "ocr" for p in pages),
                            "failed_pages": sum(p["status"] == "FAILED" for p in pages)})

    docs_by_vote: dict[str, list[dict]] = {}
    for doc in source_rows:
        refs = doc.get("ofs_vote_ids", [doc.get("ofs_vote_id", "")])
        if isinstance(refs, str):
            refs = [refs]
        for vote_id in refs:
            if vote_id:
                docs_by_vote.setdefault(str(vote_id), []).append(doc)
    coverage = []
    section_by_source: dict[str, list[dict]] = {}
    for section in section_rows:
        section_by_source.setdefault(section["source_id"], []).append(section)
    section_links = []
    for doc in source_rows:
        refs = doc.get("ofs_vote_ids", [doc.get("ofs_vote_id", "")])
        if isinstance(refs, str):
            refs = [refs]
        for vote_id in refs:
            for section in section_by_source.get(doc.get("source_id"), []):
                section_links.append({"vote_id": str(vote_id), "object_id": section["object_id"],
                                      "source_id": doc.get("source_id"), "pdf_sha256": doc.get("pdf_sha256"),
                                      "match_status": doc.get("match_status", "UNRESOLVED"),
                                      "justification": doc.get("match_justification", "Section-to-vote correspondence requires review.")})
    for vote in joined["votes"]:
        candidates = docs_by_vote.get(vote["vote_id"], [])
        source = candidates[0] if len(candidates) == 1 else None
        reasons = []
        if not source:
            reasons.append("no French Chancellerie brochure explicitly linked to this OFS vote_id" if not candidates else "multiple brochures linked; explicit document match required")
        elif source.get("extraction_status") != "EXTRACTED":
            reasons.append("brochure PDF unavailable or extraction failed")
        elif source.get("semantic_status", "NOT_VALIDATED") != "VALIDATED":
            reasons.append("semantic extraction not validated")
        if vote.get("swissvotes_status") != "MATCHED":
            reasons.append(f"Swissvotes metadata {vote.get('swissvotes_status')}")
        if not source or source.get("match_status") != "VALIDATED":
            reasons.append("OFS brochure correspondence is not validated")
        if not source or source.get("availability_status") != "CONFIRMED_PRE_VOTE":
            reasons.append("pre-vote availability is not confirmed for the current PDF version")
        if source and source.get("decision_source_sha256") != source.get("pdf_sha256"):
            reasons.append("temporal decision is missing or stale for the current PDF hash")
        if bool(vote.get("is_tiebreak_question", False)):
            reasons.append("subsidiary question excluded from model")
        coverage.append({**vote, "source_id": source.get("source_id") if source else None,
                         "pdf_sha256": source.get("pdf_sha256") if source else None,
                         "source_sha256": source.get("pdf_sha256") if source else None,
                         "decision_source_sha256": source.get("decision_source_sha256") if source else None,
                         "brochure_status": "FOUND" if source else "MISSING_OR_AMBIGUOUS",
                         "availability_status": source.get("availability_status", "INVESTIGATE") if source else None,
                         "match_status": source.get("match_status", "UNRESOLVED") if source else None,
                         "extraction_status": source.get("extraction_status", "MISSING") if source else "MISSING",
                         "semantic_status": source.get("semantic_status", "NOT_VALIDATED") if source else None,
                         "object_ids": [item["object_id"] for item in section_by_source.get(source.get("source_id"), [])] if source else [],
                         "section_count": len(section_by_source.get(source.get("source_id"), [])) if source else 0,
                         "exclusion_reasons": "; ".join(reasons)})
    pd.DataFrame(coverage).to_parquet(output / "coverage.parquet", index=False)
    pd.DataFrame(source_rows).to_parquet(output / "sources.parquet", index=False)
    pd.DataFrame(page_rows).to_parquet(output / "pages.parquet", index=False)
    pd.DataFrame(section_rows).to_parquet(output / "sections.parquet", index=False)
    pd.DataFrame(section_links, columns=["vote_id", "object_id", "source_id", "pdf_sha256", "match_status", "justification"]).to_parquet(output / "section_links.parquet", index=False)
    ofs_objects = []
    expected_records = expected.to_dict("records")
    for row in expected_records:
        row["related_vote_ids"] = _list_value(row.get("related_vote_ids"))
        row["is_tiebreak_question"] = bool(row.get("is_tiebreak_question", False))
        row["match_status"] = "UNRESOLVED"
        row["availability_status"] = "INVESTIGATE"
        row["extraction_status"] = "EXTRACTED" if docs_by_vote.get(str(row["vote_id"])) else "MISSING"
        row["semantic_status"] = "NOT_VALIDATED"
        raw_sections = [item for item in section_rows if any(link["vote_id"] == str(row["vote_id"]) and link["object_id"] == item["object_id"] for link in section_links)]
        row["council_recommendation_raw"] = raw_sections[0].get("council_recommendation_raw") if len(raw_sections) == 1 else None
        row["parliament_recommendation_raw"] = raw_sections[0].get("parliament_recommendation_raw") if len(raw_sections) == 1 else None
        ofs_objects.append(row)
    relation_sections = [{**item, "section_id": item["object_id"]} for item in section_rows]
    relation_links = [{"vote_id": item["vote_id"], "section_id": item["object_id"]}
                      for item in section_links]
    related = build_related_vote_data(ofs_objects, relation_sections, relation_links)
    related["related_votes"].to_parquet(output / "related_votes.parquet", index=False)
    related["votes_intermediate"].to_parquet(output / "votes_intermediate.parquet", index=False)
    expected_by_date = expected.groupby("vote_date").vote_id.apply(lambda values: sorted(values.astype(str))).to_dict()
    document_audit = []
    for doc in source_rows:
        expected_ids = expected_by_date.get(str(doc.get("vote_date", "")), [])
        found_count = len(section_by_source.get(doc.get("source_id"), []))
        document_audit.append({"source_id": doc.get("source_id"), "vote_date": doc.get("vote_date"),
                               "pdf_sha256": doc.get("pdf_sha256"), "ofs_vote_ids": expected_ids,
                               "expected_vote_count": len(expected_ids), "extracted_section_count": found_count,
                               "native_pages": doc.get("native_pages", 0), "ocr_pages": doc.get("ocr_pages", 0),
                               "failed_pages": doc.get("failed_pages", 0),
                               "coverage_note": ("no recognized section heading; manual layout review required" if found_count == 0 else
                                                 "section count differs from question count; related questions may share sections and mapping remains unresolved" if found_count != len(expected_ids) else
                                                 "counts agree; object-to-vote match still requires validation")})
    pd.DataFrame(document_audit).to_parquet(output / "document_audit.parquet", index=False)
    metadata = [{"source": "Swissvotes", **joined["source_provenance"]}]
    metadata[0]["source_url"] = "https://swissvotes.ch/page/dataset/swissvotes_dataset.csv"
    pd.DataFrame(metadata).to_json(output / "source_provenance.json", orient="records", indent=2)
    (output / "swissvotes_join_audit.json").write_text(json.dumps({
        "duplicate_anr_vote_ids": joined["duplicate_anr"],
        "unconvertible_anr_raw": joined["unconvertible_anr"],
        "unmatched_normalized_ids": joined["unmatched_swissvotes"],
        "out_of_scope_vote_ids": joined["out_of_scope_swissvotes"],
        "before_result_period_vote_ids": joined["before_result_period_vote_ids"],
        "future_after_local_results_vote_ids": joined["future_after_local_results_vote_ids"],
        "in_period_unmatched_vote_ids": joined["in_period_unmatched_vote_ids"],
        "expected_local_vote_ids": len(expected),
        "matched_vote_ids": sum(row["swissvotes_status"] == "MATCHED" for row in coverage),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "correction_audit.json").write_text(json.dumps(correction_audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    frame = pd.DataFrame(coverage)
    eligible, excluded = filter_model_eligible(coverage)
    pd.DataFrame(eligible).to_parquet(output / "model.parquet", index=False)
    pd.DataFrame(excluded).to_parquet(output / "model_exclusions.parquet", index=False)
    report = ["# Full-period federal explanations audit", "", "Period: French-language sources for 2011–2026.",
              f"Expected OFS vote objects: {len(frame)}", f"Chancellerie PDFs supplied: {len(source_rows)}",
              f"Swissvotes exact matches: {(frame.swissvotes_status == 'MATCHED').sum()}",
              f"Swissvotes IDs outside OFS result period: {len(joined['out_of_scope_swissvotes'])}",
              f"Swissvotes entries before local result period: {len(joined['before_result_period_vote_ids'])}",
              f"Swissvotes future entries after local result cutoff: {len(joined['future_after_local_results_vote_ids'])}",
              f"Swissvotes unmatched inside local period: {len(joined['in_period_unmatched_vote_ids'])}",
              f"Vote IDs associated with official brochure dates: {(frame.brochure_status == 'FOUND').sum()}",
              f"Distinct Chancellery brochure dates: {len(source_rows)}",
              f"Native extracted pages: {sum(int(x.get('native_pages', 0)) for x in source_rows)}",
              f"OCR fallback pages: {sum(int(x.get('ocr_pages', 0)) for x in source_rows)}",
              f"OCR failed pages: {sum(int(x.get('failed_pages', 0)) for x in source_rows)}",
              f"Vote-to-vote relation edges supplied by OFS input: {len(related['related_votes'])} (see `related_votes.parquet`; IDs retained in `votes_intermediate.parquet`)",
              f"Model-eligible rows: {len(eligible)}", "",
              "Swissvotes provides structured metadata only; summary and explanatory text are from the Chancellerie PDF. "
              "Join key rule: `str(int(Decimal(anr) * 10))` must map to one unique OFS `vote_id`, with vote date agreement; "
              "unconvertible, colliding, date-mismatched, and out-of-scope rows remain reported. "
              "Section counts are not expected to equal question counts. OCR success is technical only; semantic validation "
              "must be explicitly reviewed. No LLM is used (0 CHF).", "", "## Per-vote coverage and exclusions", ""]
    for row in coverage:
        report.append(f"- {row['vote_id']} ({row['vote_date']}): {row['exclusion_reasons'] or 'eligible'}")
    report.extend(["", "## Document-level count differences", ""])
    for doc in document_audit:
        if doc["expected_vote_count"] != doc["extracted_section_count"]:
            report.append(f"- {doc['vote_date']}: {doc['expected_vote_count']} OFS vote questions; "
                          f"{doc['extracted_section_count']} extracted brochure sections. {doc['coverage_note']}. "
                          f"OFS vote IDs: {', '.join(doc['ofs_vote_ids']) or 'none'}.")
    report.extend(["", "A section-count difference does not establish a missing brochure passage or a vote match. "
                   "No document-to-vote links are automatically validated; review the source section, date, and OFS question together."])
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ofs", type=Path, required=True, help="Read-only OFS vote reference CSV or communal parquet")
    parser.add_argument("--swissvotes", type=Path, required=True, help="Cached Swissvotes CSV")
    parser.add_argument("--sources", type=Path, required=True, help="Local PDF manifest JSON")
    parser.add_argument("--source-version", required=True, help="Swissvotes release identifier/date")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_audit(args.ofs, args.swissvotes, args.sources, args.output, source_version=args.source_version)


if __name__ == "__main__":
    main()
