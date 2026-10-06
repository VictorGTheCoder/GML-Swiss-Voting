"""Build auditable linked-vote tables without dropping subsidiary questions."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

import pandas as pd


_AUTHORITIES = ("council", "parliament")
_NO_RECOMMENDATION = re.compile(
    r"\b(?:pas de recommandation|ne (?:formule|donne|fait) pas de recommandation|"
    r"sans recommandation|aucune recommandation)\b", re.IGNORECASE
)


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _recommendation(raw: object, vote: Mapping) -> tuple[str | None, str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, "not_extracted"
    text = str(raw).strip()
    if not text:
        return None, "not_extracted"
    if _NO_RECOMMENDATION.search(_plain(text)):
        return None, "explicit_no_recommendation"

    lowered = _plain(text)
    candidates = []
    for key, aliases in (
        ("INITIATIVE", (vote.get("initiative_title"), "initiative")),
        ("COUNTERPROPOSAL", (vote.get("counterproposal_title"), "contre-projet", "contreprojet")),
    ):
        if any(alias and _plain(str(alias)) in lowered for alias in aliases):
            candidates.append(key)
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) > 1:
        return None, "multiple_targets"

    actions = []
    if re.search(r"\b(?:rejeter|rejet|refuser|refus|non)\w*\b", lowered):
        actions.append("REJECT")
    if re.search(r"\b(?:accepter|accept|approuver|approbation|oui)\w*\b", lowered):
        actions.append("ACCEPT")
    actions = list(dict.fromkeys(actions))
    if len(actions) != 1:
        return None, "ambiguous_action" if actions else "no_clear_action"

    if not candidates:
        # A single-object OFS question is a clear target only when no linked
        # proposal choices are present in the recommendation text.
        if len(vote.get("related_vote_ids", [])) <= 1:
            return f"{actions[0]}_QUESTION", "clear_single_target"
        return None, "no_clear_target"
    if len(candidates) != 1:
        return None, "multiple_targets"
    return f"{actions[0]}_{candidates[0]}", "clear_single_target"


def build_related_vote_data(
    ofs_objects: Iterable[Mapping],
    sections: Iterable[Mapping],
    section_links: Iterable[Mapping],
) -> dict[str, pd.DataFrame]:
    """Return deduplicated source sections, links, intermediate votes, and model rows.

    Input objects retain their OFS ``vote_id`` and ``is_tiebreak_question``.
    ``related_vote_ids`` is kept as supplied and also expanded to an edge table.
    A section is stored once by ``section_id`` and may be linked to any number
    of votes; a vote may in turn link to any number of sections.
    """
    objects = [dict(item) for item in ofs_objects]
    section_rows = [dict(item) for item in sections]
    link_rows = [dict(item) for item in section_links]
    ids = [str(item["vote_id"]) for item in objects]
    if len(ids) != len(set(ids)):
        raise ValueError("OFS vote_id values must be unique")
    known_ids = set(ids)
    for item in objects:
        item["vote_id"] = str(item["vote_id"])
        item["related_vote_ids"] = [str(value) for value in item.get("related_vote_ids", [])]
        unknown = set(item["related_vote_ids"]) - known_ids
        if unknown:
            raise ValueError(f"{item['vote_id']}: unknown related vote_id(s): {', '.join(sorted(unknown))}")
        if item["vote_id"] in item["related_vote_ids"]:
            raise ValueError(f"{item['vote_id']}: a vote cannot be related to itself")

    deduplicated_sections = {}
    for item in section_rows:
        item["section_id"] = str(item["section_id"])
        previous = deduplicated_sections.get(item["section_id"])
        if previous is not None and previous != item:
            raise ValueError(f"conflicting source section rows for section_id {item['section_id']}")
        deduplicated_sections[item["section_id"]] = item
    section_rows = list(deduplicated_sections.values())
    section_ids = list(deduplicated_sections)
    sections_by_id = set(section_ids)
    for link in link_rows:
        link["vote_id"] = str(link["vote_id"])
        link["section_id"] = str(link["section_id"])
        if link["vote_id"] not in known_ids:
            raise ValueError(f"section link references unknown vote_id {link['vote_id']}")
        if link["section_id"] not in sections_by_id:
            raise ValueError(f"section link references unknown section_id {link['section_id']}")
    if len({(row["vote_id"], row["section_id"]) for row in link_rows}) != len(link_rows):
        raise ValueError("section links must be unique per vote_id and section_id")

    for item in objects:
        for authority in _AUTHORITIES:
            raw_key = f"{authority}_recommendation_raw"
            target, reason = _recommendation(item.get(raw_key), item)
            item[f"{authority}_recommendation_target"] = target
            item[f"{authority}_recommendation_reason"] = reason

    edges = [
        {"vote_id": vote_id, "related_vote_id": related}
        for item in objects
        for vote_id, related in [(item["vote_id"], other) for other in item["related_vote_ids"]]
    ]
    model_rows = [item for item in objects if not bool(item.get("is_tiebreak_question", False))
                  and item.get("availability_status") == "CONFIRMED_PRE_VOTE"
                  and item.get("match_status") == "VALIDATED"
                  and item.get("extraction_status") == "EXTRACTED"
                  and item.get("semantic_status") == "VALIDATED"]
    report = (
        f"OFS objects/questions: {len(objects)}\n"
        f"Source sections: {len(section_rows)}\n"
        "Section and question counts may differ because a section can be shared by several linked votes, "
        "and one vote can reference multiple sections."
    )
    return {
        "votes_intermediate": pd.DataFrame(objects),
        "sections": pd.DataFrame(section_rows),
        "section_links": pd.DataFrame(link_rows, columns=["vote_id", "section_id"]),
        "related_votes": pd.DataFrame(edges, columns=["vote_id", "related_vote_id"]),
        "model": pd.DataFrame(model_rows),
        "report": report,
    }
