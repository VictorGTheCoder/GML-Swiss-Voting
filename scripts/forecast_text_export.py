"""Publication-aware forecast text export for model evaluation.

The temporal-decision logic is maintained in the federal_explanations package.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from scripts.federal_explanations.federal_explanations_temporal import filter_model_eligible


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


def build_forecast_text_export(rows: Iterable[Mapping[str, object]], output_dir=None) -> dict:
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
        row["text"] = row.get("text") or row.get("full_text")
        row["forecast_evidence"] = forecast_evidence
        if not row.get("vote_id") or not row["voting_date"]:
            reasons.append("object identifier or voting date is missing")
        if not isinstance(row["text"], str) or not row["text"].strip():
            reasons.append("validated object text is empty")
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
