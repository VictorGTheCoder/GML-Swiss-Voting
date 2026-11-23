"""Build a target-free review backlog for semantic labels on all V3 ballot objects."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

from scripts.common.config import ROOT
from scripts.modeling.semantic_features_v4 import (
    build_semantic_table,
    build_topic_table,
    load_annotations,
    validate_annotation_document,
)


def build_review_queue(objects, document):
    """Never consult municipal/national outcomes, model errors or candidate test scores."""
    validate_annotation_document(document)
    if not {"vote_id", "vote_date"}.issubset(objects):
        raise ValueError("Missing object identity")
    base = objects[["vote_id", "vote_date"]].copy()
    base["vote_id"] = base.vote_id.astype(str)
    if base.vote_id.duplicated().any():
        raise ValueError("Duplicate vote identity")
    canonical = build_topic_table(objects)
    build_semantic_table(objects, document)  # exact vote IDs and dates
    base = base.merge(canonical, on="vote_id", validate="one_to_one")
    reviews = {str(v["vote_id"]): v for v in document["votes"]}
    records = []
    for row in base.itertuples(index=False):
        doc = reviews.get(str(row.vote_id))
        status = "awaiting_independent_review" if doc else "needs_first_pass"
        year = pd.Timestamp(row.vote_date).year
        records.append({
            "vote_id": row.vote_id,
            "vote_date": pd.Timestamp(row.vote_date).date().isoformat(),
            "topic_leaves": row.topic_leaves,
            "review_state": status,
            "source_pdf_url": document["sources"][doc["source"]]["url"] if doc else "",
            "effect_count": len(doc["effects"]) if doc else 0,
            "review_priority": "historical_training_gap" if not doc and year < 2016 else (
                "later_unannotated" if not doc else "second_reviewer"),
        })
    return pd.DataFrame(records, columns=[
        "vote_id", "vote_date", "topic_leaves", "review_state",
        "source_pdf_url", "effect_count", "review_priority",
    ]).sort_values(["vote_date", "vote_id"]).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extras", type=Path, default=ROOT / "data/processed/municipal_v3/object_features.csv")
    parser.add_argument("--annotations", type=Path, default=ROOT / "data/annotations/yes_effects_v4.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/generated/semantic_v4/review_queue.csv")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Do not overwrite an annotation queue; choose a new location")
    objects = pd.read_csv(args.extras, dtype={"vote_id": "string"}, keep_default_na=False)
    queue = build_review_queue(objects, load_annotations(args.annotations))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(args.output, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Objects: {len(queue)}; initial: {(queue.review_state == 'needs_first_pass').sum()}; "
          f"second review: {(queue.review_state == 'awaiting_independent_review').sum()}")


if __name__ == "__main__":
    main()
