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
_BARE_OBJECT = re.compile(r"^\s*Objet\s*(?:[-–:]\s*(.*?))?\s*$", re.IGNORECASE)
_ORDINAL = re.compile(r"^\s*(Premier|Première|Premiere|Deuxième|Deuxieme|Second|Seconde|Troisième|Troisieme|Quatrième|Quatrieme|Cinquième|Cinquieme|Sixième|Sixieme|\d+(?:er|e|ème|eme))\s*$", re.IGNORECASE)


def _headings(pages: list[str]) -> tuple[list[dict], set[str]]:
    found: list[dict] = []
    bare: list[dict] = []
    formats: set[str] = set()
    flat = [(page_number, line) for page_number, page in enumerate(pages, 1)
            for line in (page or "").splitlines()]
    offsets = []
    offset = 0
    for page in pages:
        offsets.append(offset)
        offset += len((page or "").splitlines())
    for page_number, page in enumerate(pages, 1):
        for line_number, line in enumerate((page or "").splitlines()):
            modern = _MODERN.match(line)
            legacy = _LEGACY.match(line)
            plain = _BARE_OBJECT.match(line)
            ordinal_line = _ORDINAL.match(line)
            if modern:
                formats.add("MODERN")
                found.append({"order": int(modern.group(1)), "title": modern.group(2).strip(),
                              "page": page_number, "line": line_number,
                              "flat_index": offsets[page_number - 1] + line_number, "layout": "MODERN"})
            elif legacy:
                formats.add("LEGACY")
                ordinal = legacy.group(1).casefold()
                numeric = re.match(r"\d+", ordinal)
                order = int(numeric.group()) if numeric else _ORDINALS.get(ordinal, 0)
                title = legacy.group(2).strip()
                flat_index = offsets[page_number - 1] + line_number
                body_start = flat_index + 1
                if not title:
                    title_lines = []
                    marker = re.compile(r"(?i)^(?:la question|le conseil fédéral|le conseil federal|résumé|resume|sur quoi vote-t-on|arguments|texte soumis|l’objet soumis|l'objet soumis|explications pages|§)")
                    while body_start < len(flat) and len(title_lines) < 8:
                        candidate = flat[body_start][1].strip()
                        if not candidate or marker.search(candidate) or re.fullmatch(r"\d+", candidate):
                            break
                        if re.match(r"(?i)^(?:premier|première|premiere|deuxième|deuxieme|troisième|troisieme|\d+(?:er|e|ème|eme))\s+objet\b", candidate):
                            break
                        title_lines.append(candidate)
                        body_start += 1
                    title = " ".join(title_lines)
                if not title:
                    ordinal = legacy.group(1).casefold()
                    numeric = re.match(r"\d+", ordinal)
                    order = int(numeric.group()) if numeric else _ORDINALS.get(ordinal, order)
                    prior = [candidate.strip() for candidate in (page or "").splitlines()[:line_number]
                             if candidate.strip() and not re.fullmatch(r"\d+", candidate.strip())]
                    if prior and not re.match(r"(?i)^(?:votation populaire|le conseil|la question|arguments|objet)\b", prior[-1]):
                        title = prior[-1]
                found.append({"order": order, "title": title, "page": page_number,
                              "line": line_number, "flat_index": flat_index,
                              "body_start": body_start, "layout": "LEGACY"})
            elif ordinal_line and line_number + 1 < len((page or "").splitlines()) and re.match(r"(?i)^\s*objet\s*$", (page or "").splitlines()[line_number + 1]):
                ordinal = ordinal_line.group(1).casefold()
                numeric = re.match(r"\d+", ordinal)
                order = int(numeric.group()) if numeric else _ORDINALS.get(ordinal, 0)
                flat_index = offsets[page_number - 1] + line_number
                body_start = flat_index + 2
                title_lines = []
                while body_start < len(flat) and len(title_lines) < 8:
                    candidate = flat[body_start][1].strip()
                    if not candidate or re.match(r"(?i)^(?:premier|première|premiere|deuxième|deuxieme|troisième|troisieme|quatrième|quatrieme|cinquième|cinquieme|sixième|sixieme)\s*$", candidate):
                        break
                    if re.match(r"(?i)^(?:la question|le conseil|arguments|objet|résumé|resume)\b", candidate):
                        break
                    title_lines.append(candidate)
                    body_start += 1
                if title_lines:
                    formats.add("LEGACY")
                    found.append({"order": order, "title": " ".join(title_lines), "page": page_number,
                                  "line": line_number, "flat_index": flat_index,
                                  "body_start": body_start, "layout": "LEGACY"})
            elif plain:
                formats.add("LEGACY")
                bare.append({"order": 1, "title": (plain.group(1) or "").strip(),
                             "page": page_number, "line": line_number,
                             "flat_index": offsets[page_number - 1] + line_number,
                             "body_start": offsets[page_number - 1] + line_number + 1,
                             "layout": "LEGACY", "bare": True})
    # Prefer explicit numbered/titled headings over standalone `Objet` labels
    # in tables of contents. Keep bare labels only when no stronger heading exists.
    if not found and bare:
        titled_bare = [heading for heading in bare if heading["title"]]
        found.extend(titled_bare or bare[:1])
        for heading in found:
            if heading.get("bare") and not heading["title"]:
                marker = re.compile(r"(?i)^(?:la question|le conseil fédéral|le conseil federal|résumé|resume|arguments|texte soumis|l’objet soumis|l'objet soumis|explications pages|§)")
                title_lines = []
                while heading["body_start"] < len(flat) and len(title_lines) < 8:
                    candidate = flat[heading["body_start"]][1].strip()
                    if not candidate or marker.search(candidate) or re.fullmatch(r"\d+", candidate):
                        break
                    title_lines.append(candidate)
                    heading["body_start"] += 1
                heading["title"] = " ".join(title_lines)
    # Some 2011-era brochures have no object label. A question block is an
    # explicit content boundary; use its preceding page title as a single object.
    if not found:
        for page_number, page in enumerate(pages, 1):
            lines = (page or "").splitlines()
            marker_index = next((i for i, line in enumerate(lines) if re.match(r"(?i)^\s*la question à laquelle", line)), None)
            if marker_index is None:
                continue
            title_lines = [line.strip() for line in lines[:marker_index]
                           if line.strip() and not re.fullmatch(r"\d+", line.strip())]
            if title_lines:
                formats.add("LEGACY")
                found.append({"order": 1, "title": " ".join(title_lines), "page": page_number,
                              "line": 0, "flat_index": offsets[page_number - 1],
                              "body_start": offsets[page_number - 1] + marker_index,
                              "layout": "LEGACY"})
                break
    question_orders = {
        heading["order"] for heading in found
        if re.search(r"(?i)(?:la question à laquelle|acceptez-vous)", pages[heading["page"] - 1] or "")
    }
    if question_orders:
        found = [heading for heading in found
                 if heading["order"] not in question_orders
                 or re.search(r"(?i)(?:la question à laquelle|acceptez-vous)", pages[heading["page"] - 1] or "")]
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
        start = heading.get("body_start", heading["flat_index"] + 1)
        if index + 1 < len(headings):
            next_heading = headings[index + 1]
            end = next_heading["flat_index"]
        else:
            end = len(page_lines)
        body = [line for _, line in page_lines[start:end] if line.strip()]
        passage_pages = sorted({heading["page"]} | {number for number, line in page_lines[start:end] if line.strip()})
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
