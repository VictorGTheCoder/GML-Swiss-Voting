from pathlib import Path

import pandas as pd
import pytest

from scripts.modeling.semantic_features_v4 import load_annotations
from scripts.modeling.semantic_review_queue_v4 import build_review_queue

ROOT = Path(__file__).resolve().parents[1]


def test_complete_auditable_backlog_from_versioned_metadata():
    extras = pd.read_csv(
        ROOT / "data/processed/municipal_v3/object_features.csv",
        dtype={"vote_id": "string"}, keep_default_na=False,
    )
    annotations = load_annotations(ROOT / "data/annotations/yes_effects_v4.json")
    queue = build_review_queue(extras, annotations)
    assert len(queue) == 380
    assert queue.vote_id.nunique() == 380
    assert queue.review_state.value_counts().to_dict() == {
        "needs_first_pass": 338,
        "awaiting_independent_review": 42,
    }
    assert (queue.loc[queue.review_priority.eq("historical_training_gap"), "vote_date"]
            .str[:4].astype(int).lt(2016).all())
    reviewed = queue[queue.review_state.eq("awaiting_independent_review")]
    assert reviewed.source_pdf_url.str.startswith("https://www.bk.admin.ch/").all()
    assert queue.loc[queue.review_state.eq("needs_first_pass"), "source_pdf_url"].eq("").all()
    assert "yes_share" not in queue and "prediction" not in queue


def test_queue_refuses_duplicate_identifiers():
    extras = pd.DataFrame({
        "vote_id": ["6410", "6410"], "vote_date": ["2021-06-13"] * 2,
        "extra_domain_tokens_1": ["1"] * 2,
        "extra_domain_tokens_2": ["1.1"] * 2,
        "extra_domain_tokens_3": ["1.11"] * 2,
    })
    annotations = load_annotations(ROOT / "data/annotations/yes_effects_v4.json")
    with pytest.raises(ValueError, match="Duplicate"):
        build_review_queue(extras, annotations)
