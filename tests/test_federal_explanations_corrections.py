import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.federal_explanations_corrections import replay_corrections


def test_replay_applies_only_decisions_bound_to_current_source_version():
    decisions = [
        {"decision_id": "d1", "source_sha256": "current", "object_id": "obj-1",
         "field": "ofs_vote_id", "value": "6001", "justification": "The printed question matches."},
        {"decision_id": "d2", "source_sha256": "old", "object_id": "obj-2",
         "field": "ofs_vote_id", "value": "6002", "justification": "Old review."},
    ]

    result = replay_corrections("current", decisions)

    assert result["applied"] == {("obj-1", "ofs_vote_id"): "6001"}
    assert result["issues"] == [{"decision_id": "d2", "status": "STALE_SOURCE_VERSION"}]


def test_contradictory_decisions_are_reported_and_neither_is_applied():
    decisions = [
        {"decision_id": "d1", "source_sha256": "current", "object_id": "obj-1",
         "field": "ofs_vote_id", "value": "6001", "justification": "First reviewer evidence."},
        {"decision_id": "d2", "source_sha256": "current", "object_id": "obj-1",
         "field": "ofs_vote_id", "value": "6002", "justification": "Second reviewer evidence."},
    ]

    result = replay_corrections("current", decisions)

    assert result["applied"] == {}
    assert result["issues"] == [
        {"decision_id": "d1", "status": "CONTRADICTORY_DECISION", "conflicts_with": ["d2"]},
        {"decision_id": "d2", "status": "CONTRADICTORY_DECISION", "conflicts_with": ["d1"]},
    ]


def test_correction_requires_version_identity_and_justification():
    result = replay_corrections("current", [{"decision_id": "d1", "object_id": "obj-1",
        "field": "ofs_vote_id", "value": "6001", "justification": ""}])

    assert result["applied"] == {}
    assert result["issues"] == [{"decision_id": "d1", "status": "INVALID_DECISION"}]
