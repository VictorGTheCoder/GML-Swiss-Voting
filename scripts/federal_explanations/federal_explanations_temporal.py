"""Version-bound temporal review decisions and the strict model export gate."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

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
        if row.get("semantic_status") != "VALIDATED":
            reasons.append("semantic extraction is not validated")
        if bool(row.get("is_tiebreak_question", False)):
            reasons.append("subsidiary question is excluded from the main model")
        if reasons:
            row["exclusion_reason"] = "; ".join(reasons)
            excluded.append(row)
        else:
            eligible.append(row)
    return eligible, excluded


def _instant(value: object):
    """Accept calendar dates or timezone-aware ISO instants, consistently in UTC."""
    from datetime import datetime, time, timezone

    raw = str(value)
    if len(raw) == 10:
        return datetime.combine(_date(raw), time(), timezone.utc)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def build_forecast_text_export(
    rows: Iterable[Mapping[str, object]], output_dir=None, *, text_field: str | None = None
) -> dict:
    """Export reviewed object texts at an evidenced brochure-publication instant.

    Input retains the existing brochure review fields. Publication evidence must
    establish availability of the exact decision_source_sha256 version, not just
    the existence of some brochure. Ambiguous relationships remain in exclusions.
    Output records use the evaluation contract's voting_date and text names.
    """
    from collections import Counter
    import json
    from pathlib import Path

    records = [dict(row) for row in rows]
    object_counts = Counter(str(row.get("vote_id")) for row in records)
    documents, exclusions = [], []
    reason_counts = Counter()
    for source in records:
        row = dict(source)
        _, rejected = filter_model_eligible([row])
        reasons = rejected[0]["exclusion_reason"].split("; ") if rejected else []
        if object_counts[str(row.get("vote_id"))] > 1:
            reasons.append("multiple document relationships for this object require review")
        forecast_evidence = row.get("forecast_evidence") or row.get("forecast_reference")
        if not forecast_evidence:
            reasons.append("forecast publication evidence is unknown")
        if not row.get("availability_reference"):
            reasons.append("exact-version availability evidence is unknown")
        cutoff = None
        try:
            cutoff = _instant(row.get("forecast_at"))
            available = _instant(row.get("availability_at"))
            if available > cutoff:
                reasons.append("exact source version became available after forecast cutoff")
        except (ValueError, TypeError):
            reasons.append("forecast or availability instant is unknown or invalid")
        row["voting_date"] = row.get("voting_date") or row.get("vote_date")
        try:
            vote_day = _instant(row['voting_date']).replace(hour=0,minute=0,second=0,microsecond=0)
            row['voting_date'] = vote_day.date().isoformat()
            if cutoff is not None and cutoff >= vote_day:
                reasons.append('forecast cutoff is not before voting day')
        except (ValueError,TypeError):
            reasons.append('voting date is invalid')
        source_field = text_field or "text"
        if text_field is None:
            text = row.get("text") or row.get("full_text")
            source_field = "text" if row.get("text") else "full_text"
        else:
            # An explicitly requested representation never falls back to a
            # generic or fuller text field when it is absent.
            text = row.get(text_field)
        row["text"] = text
        row["text_source_field"] = source_field
        row["forecast_evidence"] = forecast_evidence
        if not row.get("vote_id") or not row["voting_date"]:
            reasons.append("object identifier or voting date is missing")
        if not isinstance(row["text"], str) or not row["text"].strip():
            reasons.append(f"requested text field {source_field!r} is empty or missing")
        if reasons:
            row["exclusion_reason"] = "; ".join(reasons)
            exclusions.append(row)
            reason_counts.update(reasons)
        else:
            documents.append(row)
    report = {
        "eligible_objects": len({row["vote_id"] for row in documents}),
        "distinct_dates": len({row["voting_date"] for row in documents}),
        "eligible_documents": len(documents),
        "excluded_records": len(exclusions),
        "exclusion_reasons": dict(sorted(reason_counts.items())),
        "status": "eligible" if documents else "empty_eligible_corpus",
    }
    result = {"documents": documents, "exclusions": exclusions, "report": report}
    if output_dir is not None:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        for name, content in result.items():
            (destination / f"{name}.json").write_text(
                json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    return result
