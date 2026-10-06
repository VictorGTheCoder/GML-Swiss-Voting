"""Exact, provenance-preserving join of Swissvotes metadata to OFS objects."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation


_FIELDS = {
    "title_fr": ("titel_off_f", "titel_kurz_f", "titel_fr", "title_fr", "titel"),
    "legal_form_fr": ("rechtsform_fr", "legal_form_fr", "typ_fr", "typ", "rechtsform"),
    "topic": ("thema", "topic", "thema_en", "d1e1"),
    "federal_council_position": ("br_pos", "br-pos", "bundesrat", "federal_council_position"),
    "national_council_position": ("nr_pos", "nr-pos", "nationalrat", "national_council_position"),
    "states_council_position": ("sr_pos", "sr-pos", "staenderat", "states_council_position"),
}


def join_swissvotes(
    ofs_objects: Iterable[Mapping],
    swissvotes_rows: Iterable[Mapping],
    *,
    source_version: str,
    source_sha256: str,
    license: str,
) -> dict:
    """Join BFS `anr` to local vote keys using the documented ×10 encoding.

    Swissvotes stores vote numbers as integers/one-decimal numbers while the
    local OFS key encodes tenths as the final digit (e.g. 554→5540, 682.1→6821).
    Only exact decimal conversion to an integer is accepted; titles are never
    used as keys. Where dates are supplied they must also agree.
    """
    ofs = [dict(row) for row in ofs_objects]
    rows = [dict(row) for row in swissvotes_rows]
    vote_ids = [str(row.get("vote_id", "")) for row in ofs]
    if not all(vote_ids) or len(set(vote_ids)) != len(vote_ids):
        raise ValueError("OFS vote_id values must be present and unique")

    def normalized_id(value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        try:
            encoded = Decimal(raw) * 10
        except InvalidOperation:
            return ""
        if not encoded.is_finite() or encoded != encoded.to_integral_value():
            return ""
        return str(int(encoded))

    raw_ids = [str(row.get("anr", "")).strip() for row in rows]
    ids = [normalized_id(value) for value in raw_ids]
    counts = Counter(value for value in ids if value)
    row_by_id = {value: row for value, row in zip(ids, rows) if value and counts[value] == 1}
    raw_by_id: dict[str, list[str]] = {}
    for value, raw in zip(ids, raw_ids):
        if value:
            raw_by_id.setdefault(value, []).append(raw)
    indexed = {str(row.get("vote_id")): row for row in ofs}
    provenance = {
        "source": "Swissvotes", "source_version": source_version,
        "source_sha256": source_sha256, "license": license,
    }
    for vote in ofs:
        vote_id = str(vote["vote_id"])
        vote["vote_id"] = vote_id
        source_id = vote_id if counts[vote_id] == 1 else ""
        if counts[vote_id] > 1:
            vote["swissvotes_status"] = "DUPLICATE_ANR"
        elif not source_id and not any(ids):
            vote["swissvotes_status"] = "MISSING_ANR"
        elif not source_id or source_id not in {key for key in ids if key}:
            vote["swissvotes_status"] = "UNMATCHED_ANR"
        else:
            source = row_by_id[source_id]
            expected_date = str(vote.get("vote_date", ""))[:10]
            source_date = str(source.get("datum", source.get("vote_date", ""))).strip()
            if source_date and "." in source_date:
                from datetime import datetime
                try:
                    source_date = datetime.strptime(source_date, "%d.%m.%Y").date().isoformat()
                except ValueError:
                    pass
            if expected_date and source_date and expected_date != source_date:
                vote["swissvotes_status"] = "DATE_MISMATCH"
            else:
                vote["swissvotes_status"] = "MATCHED"
        raw_source = row_by_id.get(source_id) if source_id and counts[source_id] == 1 else None
        source = raw_source if vote["swissvotes_status"] == "MATCHED" else None
        vote["swissvotes_anr_raw"] = raw_source.get("anr") if raw_source else None
        vote["swissvotes_anr_raw_candidates"] = raw_by_id.get(vote_id, [])
        vote["swissvotes_anr_vote_id"] = source_id or None
        vote["swissvotes_provenance"] = provenance.copy() if source else None
        for target, aliases in _FIELDS.items():
            value = next((source[key] for key in aliases if source and key in source and str(source[key]).strip()), None)
            vote[f"swissvotes_{target}"] = value
            vote.setdefault("field_provenance", {})[f"swissvotes_{target}"] = provenance.copy() if value is not None else None
            if value is not None:
                missing_reason = None
            elif vote["swissvotes_status"] == "DATE_MISMATCH":
                missing_reason = "Swissvotes metadata not joined because its date mismatches the local OFS vote date"
            else:
                missing_reason = "Swissvotes source field is absent or blank"
            vote.setdefault("field_missing_reasons", {})[f"swissvotes_{target}"] = missing_reason
        topic_codes = [source[key] for key in ("d1e1", "d1e2", "d1e3", "d2e1", "d2e2", "d2e3", "d3e1", "d3e2", "d3e3")
                       if source and source.get(key, "")]
        vote["swissvotes_topic_codes"] = topic_codes
        vote["field_provenance"]["swissvotes_topic_codes"] = provenance.copy() if topic_codes else None
        vote["field_missing_reasons"]["swissvotes_topic_codes"] = None if topic_codes else "Swissvotes topic-code fields are absent or blank"
        # Brochure provenance belongs to its document record, never Swissvotes.
        vote.setdefault("brochure_source", None)

    unmatched = sorted({value for value in ids if value and value not in indexed})
    def swiss_date(row: Mapping) -> str:
        value = str(row.get("datum", row.get("vote_date", ""))).strip()
        if "." in value:
            from datetime import datetime
            try:
                return datetime.strptime(value, "%d.%m.%Y").date().isoformat()
            except ValueError:
                return ""
        return value[:10]

    lower = min((str(row.get("vote_date", ""))[:10] for row in ofs if row.get("vote_date")), default="2011-01-01")
    upper = max((str(row.get("vote_date", ""))[:10] for row in ofs if row.get("vote_date")), default="2026-12-31")
    before = sorted({value for value, row in zip(ids, rows) if value and value not in indexed and swiss_date(row) < lower})
    future = sorted({value for value, row in zip(ids, rows) if value and value not in indexed and swiss_date(row) > upper})
    in_period = sorted({value for value, row in zip(ids, rows) if value and value not in indexed
                        and lower <= swiss_date(row) <= upper})
    return {"votes": ofs, "unmatched_swissvotes": unmatched,
            "duplicate_anr": sorted(value for value, count in counts.items() if count > 1),
            "unconvertible_anr": sorted({raw for raw, value in zip(raw_ids, ids) if raw and not value}),
            "out_of_scope_swissvotes": sorted(set(ids) - set(indexed) - {""}),
            "before_result_period_vote_ids": before,
            "future_after_local_results_vote_ids": future,
            "in_period_unmatched_vote_ids": in_period,
            "source_provenance": provenance}
