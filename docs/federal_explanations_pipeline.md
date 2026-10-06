# Federal explanations pipeline (first modern object)

This local, offline entry point reconstructs one modern French one-object
brochure against a small OFS reference. It preserves source PDFs by SHA-256 and
writes `coverage.parquet`, `sections.parquet`, `section_links.parquet`, the
strictly filtered `model.parquet`, and `report.md`.

Install the dependencies in `environment.yml`, then run:

```bash
python scripts/federal_explanations.py \
  --ofs /path/to/ofs.csv \
  --sources /path/to/sources.json \
  --output /path/to/output
```

The OFS CSV has `vote_id` (preserved as text), `vote_date`, `question_fr`, and
`is_tiebreak_question`. The JSON manifest is an object with a `documents` list;
each item contains `source_id`, local `pdf_path`, `official_url`, `vote_date`,
`language` (`fr`), ISO `collected_at`, `availability_status`,
`availability_evidence`, `ofs_vote_id`, `match_status`, and
`match_justification`. Use `CONFIRMED_PRE_VOTE` only when the evidence supports
public availability of this PDF version before the vote. A match is model
eligible only when explicitly marked `VALIDATED` and the exact OFS question
title agrees with the extracted title. Unproven timing, proposed/ambiguous
matches, missing sources, and tie-break rows remain represented in coverage and
the report but are excluded from the model export.

The first parser supports a modern text PDF containing one section with these
line labels: `Objet N: title`, `Résumé officiel: ...`, `Texte complet: ...`,
`Conseil fédéral: ...`, and `Parlement: ...`. Missing optional fields are
exported as empty text. Page references are one-based PDF pages containing text.
Scanned pages are supported by the optional page-level extractor in
`scripts/federal_explanations_ocr.py`. It uses native PDF text when a page has
usable text and invokes local Tesseract OCR only for pages without it. Each page
record has the same fields (`page_number`, `text`, `method`, `status`, `error`,
and `semantic_status`), including failed OCR pages so callers can report exact
page references. A successful OCR transcription has
`semantic_status: NOT_VALIDATED`; a person must still check the words,
section boundaries, vote correspondence, and eligibility. No LLM or remote
service is called. The original PDF is only read, not rewritten.

OCR is optional and is not installed by the standard Conda environment. Install
the Python bindings in that environment:

```bash
python -m pip install pymupdf pytesseract Pillow
```

Then install the Tesseract OCR executable and French language data (`fra`)
using your operating system's package manager. Confirm the executable is on
`PATH` and that `tesseract --list-langs` includes `fra`.
Without these optional components, native text extraction still works; pages
needing OCR receive a page-level `FAILED` status with the dependency error.

Multi-object or older layouts, archive crawling, and versioned human review
decisions remain later extensions. Each pipeline run writes deterministic
tables and does not overwrite original content: the SHA-256 names each retained
PDF version.

## Linked OFS objects

Use `scripts/federal_explanations_relations.py` when a brochure contains linked
objects such as an initiative, counterproposal, and subsidiary question. Its
`build_related_vote_data(ofs_objects, sections, section_links)` API accepts one
row per OFS `vote_id`, preserves `related_vote_ids` and the authoritative
`is_tiebreak_question` value, and returns `votes_intermediate`, deduplicated
`sections`, `section_links`, `related_votes`, and `model` tables. A section is
stored once by `section_id`; multiple vote links may point to it, and each vote
may point to multiple sections. The subsidiary question and its extracted
content remain in `votes_intermediate`; only the model table filters out rows
marked as tie-break questions. The model table also applies the existing
pre-vote availability, validated correspondence, and extraction eligibility
conditions.

Each authority's `*_recommendation_raw` value is preserved. The corresponding
`*_recommendation_target` is populated only when one action and one proposal
target are clear; otherwise it stays null and `*_recommendation_reason` records
why, including explicit no-recommendation and unextracted cases. An empty or
ambiguous recommendation is never converted to an assumed position. The
returned report states why section counts may differ from OFS question counts:
several votes can share one section, and a vote can link to several sections.

## Temporal review and model eligibility

`scripts/federal_explanations_temporal.py` provides a version-bound review
contract independent of the extraction CLI. `decide_temporal_status(vote_date,
source_sha256, evidence)` returns one of `CONFIRMED_PRE_VOTE`, `INVESTIGATE`, or
`POST_VOTE`, together with the selected evidence kind, reference, evidence date,
justification, and exact PDF SHA-256. Supported evidence kinds are
`public_release`/`public_availability` before the vote and
`public_publication`/`content_change` after it. Collection, document closing,
archive migration, and page-update dates are insufficient by themselves.
Evidence on the vote date, missing dates, and contradictory qualifying evidence
remain `INVESTIGATE`. A page update cannot establish a post-vote content change.

Use `apply_temporal_decision(decision, current_source_sha256)` before applying a
saved review. A different PDF hash marks the decision stale and resets its
status to `INVESTIGATE`. To build the main model subset,
`filter_model_eligible(rows)` returns `(eligible, exclusions)`. Rows require a
confirmed decision bound to the current source hash, validated OFS matching,
validated extraction (`EXTRACTED`), and a non-subsidiary question. Every
excluded row is retained with an `exclusion_reason`; an empty eligible list is
valid and should be reported as an empty model export.
