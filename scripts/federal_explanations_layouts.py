"""Conservative, auditable structure and OFS matching helpers.

The parser deliberately returns passages with their source pages instead of
flattening a whole brochure into one object. It only recognizes explicit
object headings; unfamiliar layouts are left for review.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher


_ORDINALS = {
    "premier": 1, "première": 1, "premiere": 1,
    "deuxième": 2, "deuxieme": 2, "second": 2, "seconde": 2,
    "troisième": 3, "troisieme": 3,
    "quatrième": 4, "quatrieme": 4,
    "cinquième": 5, "cinquieme": 5,
    "sixième": 6, "sixieme": 6,
}
_MODERN = re.compile(r"^\s*Objet\s+(\d+)\s*:\s*(.*?)\s*$", re.IGNORECASE)
_LEGACY = re.compile(r"^\s*(Premier|Première|Premiere|Deuxième|Deuxieme|Second|Seconde|Troisième|Troisieme|Quatrième|Quatrieme|Cinquième|Cinquieme|Sixième|Sixieme|\d+(?:er|e|ème|eme))\s+objet\s*:?\s*(.*?)\s*$", re.IGNORECASE)


def _headings(pages: list[str]) -> tuple[list[dict], set[str]]:
    found: list[dict] = []
    formats: set[str] = set()
    for page_number, page in enumerate(pages, 1):
        for line_number, line in enumerate((page or "").splitlines()):
            modern = _MODERN.match(line)
            legacy = _LEGACY.match(line)
            if modern:
                formats.add("MODERN")
                found.append({"order": int(modern.group(1)), "title": modern.group(2).strip(),
                              "page": page_number, "line": line_number, "layout": "MODERN"})
            elif legacy:
                formats.add("LEGACY")
                ordinal = legacy.group(1).casefold()
                numeric = re.match(r"\d+", ordinal)
                order = int(numeric.group()) if numeric else _ORDINALS.get(ordinal, 0)
                title = legacy.group(2).strip()
                found.append({"order": order, "title": title, "page": page_number,
                              "line": line_number, "layout": "LEGACY"})
    return found, formats


def detect_layout(pages: list[str]) -> str:
    """Return MODERN, LEGACY, MIXED, or UNRECOGNIZED from explicit headings."""
    _, formats = _headings(pages)
    if len(formats) > 1:
        return "MIXED"
    return next(iter(formats), "UNRECOGNIZED")


def extract_objects(pages: list[str], *, source_id: str = "source", source_sha256: str = "") -> dict:
    """Extract recognized objects in brochure order, retaining noncontiguous passages."""
    headings, formats = _headings(pages)
    layout = "MIXED" if len(formats) > 1 else next(iter(formats), "UNRECOGNIZED")
    objects_by_order: dict[int, dict] = {}
    for index, heading in enumerate(headings):
        page_lines = [(page_number, line) for page_number, page in enumerate(pages, 1)
                      for line in (page or "").splitlines()]
        start = sum(len((page or "").splitlines()) for page in pages[:heading["page"] - 1]) + heading["line"]
        if index + 1 < len(headings):
            next_heading = headings[index + 1]
            end = sum(len((page or "").splitlines()) for page in pages[:next_heading["page"] - 1]) + next_heading["line"]
        else:
            end = len(page_lines)
        body = [line for _, line in page_lines[start + 1:end] if line.strip()]
        passage_pages = sorted({number for number, line in page_lines[start:end] if line.strip()})
        passage = {"pages": passage_pages, "text": "\n".join(body).strip()}
        obj = objects_by_order.setdefault(heading["order"], {
            "object_id": f"{source_id}:{source_sha256[:12] or 'unversioned'}:{heading['order']}",
            "order": heading["order"], "title": heading["title"], "layout": heading["layout"],
            "passages": [], "source_pages": [],
        })
        # A conflicting repeated title at the same order is itself auditable.
        if obj["title"].casefold() != heading["title"].casefold():
            obj["title_conflict"] = True
            obj["alternate_titles"] = sorted(set(obj.get("alternate_titles", []) + [heading["title"]]))
        obj["passages"].append(passage)
        obj["source_pages"] = sorted(set(obj["source_pages"] + passage_pages))
    return {"layout": layout, "structure_status": "REVIEW" if layout in {"UNRECOGNIZED", "MIXED"} else "RECOGNIZED",
            "objects": sorted(objects_by_order.values(), key=lambda item: item["order"])}


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


def propose_matches(title: str, ofs_objects: list[dict]) -> dict:
    """Return similarity ranked proposals; this function never validates a match."""
    normalized = _normalize(title)
    candidates = []
    for row in ofs_objects:
        question = str(row.get("question_fr", ""))
        score = SequenceMatcher(None, normalized, _normalize(question)).ratio()
        if score >= 0.5:
            candidates.append({"vote_id": str(row["vote_id"]), "question_fr": question,
                               "similarity": round(score, 4), "status": "PROPOSED"})
    candidates.sort(key=lambda candidate: (-candidate["similarity"], candidate["vote_id"]))
    top = candidates[0]["similarity"] if candidates else 0
    ambiguous = len(candidates) > 1 and (candidates[1]["similarity"] == top or top - candidates[1]["similarity"] < 0.08)
    status = "AMBIGUOUS" if ambiguous else "PROPOSED" if candidates else "UNRESOLVED"
    return {"status": status, "candidates": candidates,
            "justification": "Similarity ranks review candidates only; a human decision is required."}


def build_coverage(expected_vote_ids: list[str], links: list[dict]) -> list[dict]:
    """Keep every expected OFS ID visible and mark missing/unvalidated rows excluded."""
    result = []
    for vote_id in expected_vote_ids:
        matching = [link for link in links if str(link.get("ofs_vote_id")) == str(vote_id)]
        ids = sorted({str(link["object_id"]) for link in matching if link.get("object_id")})
        if not matching:
            status, excluded, reason = "MISSING", True, "no extracted object linked to OFS vote_id"
        elif all(link.get("status") == "VALIDATED" for link in matching):
            status, excluded, reason = "FOUND", False, ""
        else:
            status, excluded, reason = "FOUND", True, "OFS correspondence is not validated"
        result.append({"vote_id": str(vote_id), "coverage_status": status, "object_ids": ids,
                       "model_excluded": excluded, "reason": reason})
    return result
