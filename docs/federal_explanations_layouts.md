# Layout reconstruction and human corrections

`scripts/federal_explanations_layouts.py` handles the structure stage separately
from the first-object pipeline entry point. Call `extract_objects(pages,
source_id=..., source_sha256=...)` with one extracted-text string per PDF page.
It recognizes modern `Objet N: title` headings and a bounded set of older
French ordinal headings such as `Premier objet : title`. Each result includes a
source-version-bound `object_id`, its displayed order and title, page references,
and ordered passages. A repeated heading for the same object adds another
passage; it does not merge in text from a different numbered object.

`detect_layout` returns `MODERN`, `LEGACY`, `MIXED`, or `UNRECOGNIZED`.
`extract_objects` labels unknown or mixed structures `REVIEW` and does not infer
objects without explicit headings. A repeated order with a different title is
preserved with `title_conflict` and `alternate_titles` so the structure can be
reviewed. Page numbers are one-based. Pages between object headings remain with
the current passage; a heading for another object closes that passage.

`propose_matches(title, ofs_objects)` ranks likely OFS rows for review. Every
returned candidate has status `PROPOSED`; a close tie makes the result
`AMBIGUOUS`. Similarity never validates a link. A later human correction must
provide the actual decision and its justification. `build_coverage` accepts the
complete expected OFS ID list and links, preserving missing rows and explicitly
excluding missing or unvalidated links from the model.

`scripts/federal_explanations_corrections.py` replays decisions shaped as:

```json
{
  "decision_id": "review-001",
  "source_sha256": "<sha256 of the exact source PDF version>",
  "object_id": "<source-id>:<hash-prefix>:<order>",
  "field": "ofs_vote_id",
  "value": "6001",
  "justification": "The printed question and official object title agree."
}
```

`replay_corrections(current_sha256, decisions)` applies a decision only when
the source hash matches and all required fields, including a justification, are
present. It reports stale source versions and invalid records. Different values
for the same object and field are both reported as `CONTRADICTORY_DECISION` and
neither is applied. The replay output keeps its issues separate from applied
values for audit and downstream review.

This module recognizes explicit text headings; it does not perform OCR or claim
to recognize every historical design. Unknown scans and layouts therefore stay
unresolved for the extraction and coverage stages to report.
