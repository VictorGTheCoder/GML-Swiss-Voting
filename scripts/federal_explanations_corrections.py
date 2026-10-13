"""Replay version-bound human decisions without silently resolving conflicts."""

from __future__ import annotations

from collections import defaultdict


_REQUIRED = ("decision_id", "source_sha256", "object_id", "field", "value", "justification")


def replay_corrections(source_sha256: str, decisions: list[dict]) -> dict:
    """Apply valid decisions for this exact source version and report unsafe ones."""
    issues = []
    current = []
    for decision in decisions:
        decision_id = str(decision.get("decision_id", ""))
        if any(not decision.get(key) for key in _REQUIRED):
            issues.append({"decision_id": decision_id, "status": "INVALID_DECISION"})
        elif decision["source_sha256"] != source_sha256:
            issues.append({"decision_id": decision_id, "status": "STALE_SOURCE_VERSION"})
        else:
            current.append(decision)

    groups = defaultdict(list)
    for decision in current:
        groups[(decision["object_id"], decision["field"])].append(decision)

    applied = {}
    for key, group in groups.items():
        values = {str(decision["value"]) for decision in group}
        if len(values) > 1:
            for decision in group:
                issues.append({"decision_id": str(decision["decision_id"]),
                               "status": "CONTRADICTORY_DECISION",
                               "conflicts_with": sorted(str(other["decision_id"]) for other in group
                                                         if other is not decision)})
        else:
            applied[key] = group[0]["value"]
    return {"applied": applied, "issues": issues}
