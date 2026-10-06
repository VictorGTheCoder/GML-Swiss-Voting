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
Scanned PDFs/OCR, multi-object or older layouts, archive crawling, and versioned
human review decisions are later extensions. Each run writes deterministic
tables and does not overwrite original content: the SHA-256 names each retained
PDF version.
