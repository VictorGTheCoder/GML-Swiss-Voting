"""Version-bound temporal review decisions and the strict model export gate."""

from __future__ import annotations

from datetime import date
from collections.abc import Iterable, Mapping

STATUSES = ("CONFIRMED_PRE_VOTE", "INVESTIGATE", "POST_VOTE")
_PRE_VOTE_KINDS = {"public_release", "public_availability"}
_POST_VOTE_KINDS = {"public_publication", "content_change"}
_WEAK_KINDS = {"collection", "closing", "archive_migration", "page_update"}


def _date(value: object) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid ISO date: {value!r}") from error


def decide_temporal_status(
    vote_date: str,
    source_sha256: str,
    evidence: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Assess evidence for one exact source version and preserve the review record.

    Evidence kinds are intentionally explicit. Archive operations and page
    metadata do not prove either public availability or a content change.
    Contradictory qualifying evidence always requires investigation.
    """
    vote_day = _date(vote_date)
    if not source_sha256:
        raise ValueError("source_sha256 is required to bind a temporal decision")
    records = [dict(item) for item in evidence]
    qualified: list[tuple[str, date, dict[str, object]]] = []
    for item in records:
        kind = str(item.get("kind", ""))
        if kind not in _PRE_VOTE_KINDS | _POST_VOTE_KINDS | _WEAK_KINDS:
            continue
        if kind in _WEAK_KINDS:
            continue
        try:
            observed = _date(item.get("date"))
        except ValueError:
            continue
        if kind in _PRE_VOTE_KINDS and observed < vote_day:
            qualified.append(("CONFIRMED_PRE_VOTE", observed, item))
        elif kind in _POST_VOTE_KINDS and observed > vote_day:
            qualified.append(("POST_VOTE", observed, item))
    categories = {item[0] for item in qualified}
    status = next(iter(categories)) if len(categories) == 1 else "INVESTIGATE"
    chosen = qualified[0][2] if len(categories) == 1 and qualified else (records[0] if records else {})
    reason = str(chosen.get("justification", ""))
    if len(categories) > 1:
        reason = "Contradictory evidence supports both pre-vote availability and post-vote change."
    elif not qualified:
        reason = reason or "No qualifying evidence establishes public availability or post-vote content change."
    return {
        "status": status,
        "source_sha256": source_sha256,
        "evidence": chosen.get("kind", ""),
        "reference": chosen.get("reference", ""),
        "evidence_date": chosen.get("date", ""),
        "justification": reason,
    }


def apply_temporal_decision(decision: Mapping[str, object], current_source_sha256: str) -> dict[str, object]:
    """Apply only a decision attached to the current PDF hash; stale ones reopen."""
    applied = dict(decision)
    stale = applied.get("source_sha256") != current_source_sha256
    applied["decision_stale"] = stale
    if stale:
        applied["status"] = "INVESTIGATE"
        applied["justification"] = "Decision is stale because the source PDF hash changed. " + str(
            applied.get("justification", "")
        )
    return applied


def filter_model_eligible(rows: Iterable[Mapping[str, object]]) -> tuple[list[dict], list[dict]]:
    """Split retained rows into eligible model rows and auditable exclusions."""
    eligible: list[dict] = []
    excluded: list[dict] = []
    for source in rows:
        row = dict(source)
        reasons = []
        if row.get("availability_status") != "CONFIRMED_PRE_VOTE":
            reasons.append("temporal availability is not confirmed pre-vote")
        if not row.get("source_sha256") or row.get("source_sha256") != row.get("decision_source_sha256"):
            reasons.append("temporal decision is missing or bound to a different PDF hash")
        if row.get("match_status") != "VALIDATED":
            reasons.append("OFS correspondence is not validated")
        if row.get("extraction_status") != "EXTRACTED":
            reasons.append("source extraction is not validated")
        if bool(row.get("is_tiebreak_question", False)):
            reasons.append("subsidiary question is excluded from the main model")
        if reasons:
            row["exclusion_reason"] = "; ".join(reasons)
            excluded.append(row)
        else:
            eligible.append(row)
    return eligible, excluded
