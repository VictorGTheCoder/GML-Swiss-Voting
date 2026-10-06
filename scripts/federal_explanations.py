"""Build a reproducible local corpus of modern federal voting explanations.

The initial adapter handles one modern, French, one-object brochure per manifest
entry. Human-supplied metadata is deliberately explicit: PDF text never proves
pre-vote availability or an OFS match by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import pandas as pd
import pdfplumber

try:
    from .federal_explanations_relations import _recommendation
except ImportError:
    from federal_explanations_relations import _recommendation


def _pdf_pages(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def _section_fields(pages: list[str]) -> dict:
    text = "\n".join(pages)
    match = re.search(r"(?im)^Objet\s+(\d+)\s*:\s*(.+?)\s*$", text)
    if not match:
        raise ValueError("modern one-object section heading not found (expected 'Objet N: title')")
    start = match.start()
    later = re.search(r"(?im)^Objet\s+\d+\s*:", text[match.end():])
    end = match.end() + later.start() if later else len(text)
    section = text[start:end]

    def field(label: str) -> str:
        aliases = {"Résumé officiel": "Resume officiel", "Conseil fédéral": "Conseil federal"}
        actual = label
        found = re.search(rf"(?ims)^{re.escape(actual)}\s*:\s*(.*?)(?=^(?:Résumé officiel|Resume officiel|Texte complet|Conseil fédéral|Conseil federal|Parlement)\s*:|\Z)", section)
        if not found and label in aliases:
            actual = aliases[label]
            found = re.search(rf"(?ims)^{re.escape(actual)}\s*:\s*(.*?)(?=^(?:Résumé officiel|Resume officiel|Texte complet|Conseil fédéral|Conseil federal|Parlement)\s*:|\Z)", section)
        return " ".join(found.group(1).split()) if found else ""

    return {
        "section_order": int(match.group(1)),
        "title": match.group(2).strip(),
        "summary_official": field("Résumé officiel"),
        "full_text": field("Texte complet"),
        "council_recommendation_raw": field("Conseil fédéral"),
        "parliament_recommendation_raw": field("Parlement"),
        "source_pages": ",".join(str(i + 1) for i, page in enumerate(pages) if page.strip()),
    }


def _recommendation_target(value: str) -> str | None:
    target, _ = _recommendation(value, {"related_vote_ids": []})
    return target.split("_", 1)[0] if target else None


def build(ofs_path: Path, sources_path: Path, output: Path) -> None:
    ofs = pd.read_csv(ofs_path, dtype={"vote_id": "string"})
    required = {"vote_id", "vote_date", "question_fr", "is_tiebreak_question"}
    if not required.issubset(ofs.columns):
        raise ValueError(f"OFS CSV missing columns: {', '.join(sorted(required - set(ofs.columns)))}")
    if ofs["vote_id"].duplicated().any():
        raise ValueError("OFS vote_id values must be unique")

    manifest = json.loads(sources_path.read_text(encoding="utf-8"))
    docs = manifest.get("documents", [])
    output.mkdir(parents=True, exist_ok=True)
    originals = output / "originals"
    originals.mkdir(exist_ok=True)
    sections: list[dict] = []
    links: list[dict] = []
    document_by_vote: dict[str, dict] = {}
    for doc in docs:
        if doc.get("language") != "fr":
            raise ValueError(f"{doc.get('source_id')}: only French sources are supported")
        source = Path(doc["pdf_path"])
        if not source.is_file():
            raise ValueError(f"PDF not found: {source}")
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        preserved = originals / f"{digest}.pdf"
        if not preserved.exists():
            shutil.copyfile(source, preserved)
        pages = _pdf_pages(source)
        extracted = _section_fields(pages)
        vote_id = str(doc.get("ofs_vote_id", ""))
        matching = ofs[ofs["vote_id"] == vote_id]
        match_status = doc.get("match_status", "UNRESOLVED")
        match_reason = doc.get("match_justification", "")
        if len(matching) != 1:
            match_status = "UNRESOLVED"
            match_reason = "OFS identifier is absent or does not identify exactly one row"
        elif str(matching.iloc[0]["question_fr"]).strip().casefold() != extracted["title"].casefold():
            if match_status == "VALIDATED":
                match_status = "PROPOSED"
            match_reason = match_reason or "OFS question title differs from extracted section title"
        section_id = f"{doc['source_id']}:{extracted['section_order']}:{digest[:12]}"
        section = {
            "section_id": section_id, "source_id": doc["source_id"], **extracted,
            "extraction_status": "EXTRACTED",
            "pdf_sha256": digest, "official_url": doc["official_url"],
            "vote_date": str(doc["vote_date"]), "language": doc["language"],
            "collected_at": doc["collected_at"], "availability_status": doc.get("availability_status", "INVESTIGATE"),
            "availability_evidence": doc.get("availability_evidence", ""),
            "semantic_status": doc.get("semantic_status", "NOT_VALIDATED"),
            "match_status": match_status, "match_justification": match_reason,
            "council_recommendation_target": _recommendation_target(extracted["council_recommendation_raw"]),
            "parliament_recommendation_target": _recommendation_target(extracted["parliament_recommendation_raw"]),
            "council_recommendation_reason": _recommendation(extracted["council_recommendation_raw"], {})[1],
            "parliament_recommendation_reason": _recommendation(extracted["parliament_recommendation_raw"], {})[1],
        }
        sections.append(section)
        links.append({"section_id": section_id, "ofs_vote_id": vote_id, "match_status": match_status,
                      "justification": match_reason})
        if vote_id:
            document_by_vote[vote_id] = {**doc, "availability_status": section["availability_status"],
                                         "match_status": match_status, "match_justification": match_reason,
                                         "section_id": section_id}

    coverage = []
    eligible_ids = set()
    for _, row in ofs.iterrows():
        vote_id = str(row["vote_id"])
        doc = document_by_vote.get(vote_id)
        reasons = []
        if doc is None:
            status = "MISSING"
            reasons.append("no French brochure supplied")
        else:
            status = "FOUND"
            if doc["availability_status"] != "CONFIRMED_PRE_VOTE":
                reasons.append("pre-vote availability not confirmed")
            if doc["match_status"] != "VALIDATED":
                if doc["match_status"] in {"PROPOSED", "AMBIGUOUS"}:
                    reasons.append(f"ambiguous OFS correspondence ({doc['match_status']})")
                else:
                    reasons.append(f"OFS correspondence not validated ({doc['match_status']})")
            if doc.get("semantic_status") != "VALIDATED":
                reasons.append("semantic extraction is not validated")
            if bool(row["is_tiebreak_question"]):
                reasons.append("tie-break question excluded from model")
        if not reasons:
                eligible_ids.add(vote_id)
        coverage.append({"vote_id": vote_id, "vote_date": str(row["vote_date"]), "question_fr": row["question_fr"],
                         "coverage_status": status, "source_id": doc.get("source_id") if doc else None,
                         "availability_status": doc.get("availability_status") if doc else None,
                         "match_status": doc.get("match_status") if doc else None,
                         "exclusion_reasons": "; ".join(reasons)})

    section_frame = pd.DataFrame(sections)
    coverage_frame = pd.DataFrame(coverage)
    links_frame = pd.DataFrame(links, columns=["section_id", "ofs_vote_id", "match_status", "justification"])
    model = section_frame[section_frame.get("section_id", pd.Series(dtype=str)).isin(
        {link["section_id"] for link in links if link["ofs_vote_id"] in eligible_ids}
    )].copy() if sections else section_frame
    coverage_frame.to_parquet(output / "coverage.parquet", index=False)
    section_frame.to_parquet(output / "sections.parquet", index=False)
    links_frame.to_parquet(output / "section_links.parquet", index=False)
    model.to_parquet(output / "model.parquet", index=False)
    report = ["# Federal explanations pipeline report", "", f"OFS objects: {len(coverage_frame)}",
              f"Sections extracted: {len(section_frame)}", f"Eligible model rows: {len(model)}", "",
              "## Coverage and exclusions", "",
              "Brochure text is sourced from the Chancellerie PDF; Swissvotes metadata is supplemental. "
              "Automated extraction does not constitute semantic validation.", ""]
    for item in coverage:
        report.append(f"- `{item['vote_id']}` {item['coverage_status']}: {item['exclusion_reasons'] or 'eligible'}")
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct French federal voting explanations from local PDFs")
    parser.add_argument("--ofs", type=Path, required=True, help="OFS CSV with vote_id, vote_date, question_fr, is_tiebreak_question")
    parser.add_argument("--sources", type=Path, required=True, help="Local JSON manifest of source metadata")
    parser.add_argument("--output", type=Path, required=True, help="Output directory for Parquet tables and report")
    args = parser.parse_args()
    build(args.ofs, args.sources, args.output)


if __name__ == "__main__":
    main()
