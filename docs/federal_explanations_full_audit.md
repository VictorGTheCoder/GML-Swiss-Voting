# Federal explanations: 2011–2026 collection and replay

The scope is French-language Federal Chancellery brochures for federal votes
from 2011 through 2026. Swissvotes is a supplemental metadata source under CC
BY 4.0; its dated CSV and SHA-256 are retained in provenance. The official
brochure remains the source for its summary, arguments, and explanatory text.
No LLM is used (0 CHF). Structured arguments are deferred.

## Collect, then replay offline

Use the read-only local OFS roster (`data/processed/votes_communes.parquet`):

```bash
python scripts/collect_federal_explanations.py \
  --ofs data/processed/votes_communes.parquet \
  --manifest data/raw/federal_explanations_sources.json \
  --cache data/raw/federal_explanations_pdf_cache
```

The collector lists PDFs from the [official Chancellery archive](https://www.bk.admin.ch/fr/compilation-des-explications-du-conseil-federal-depuis-1978),
downloads French PDFs for 2011–2026, verifies the PDF signature, hashes each
byte stream, and caches it under its SHA-256. Collection time is recorded as
collection provenance; it never confirms pre-vote availability. The manifest
links a brochure date to the OFS vote IDs on that date, but leaves object-level
matching, semantic validation, and temporal review unresolved.

Download the CSV from the [Swissvotes dataset page](https://swissvotes.ch/page/dataset)
to a local cache. Its published file has a semicolon delimiter. Record its
release name/date, CC BY 4.0 license, and SHA-256. Then run the audit:

```bash
python scripts/audit_federal_explanations_period.py \
  --ofs data/processed/votes_communes.parquet \
  --swissvotes data/raw/swissvotes.csv \
  --sources data/raw/federal_explanations_sources.json \
  --source-version 'DATASET CSV YYYY-MM-DD' \
  --output data/processed/federal_explanations
```

After collection, replay requires only the cached PDF files, manifest, OFS
reference, and Swissvotes CSV; no network access is used. Parquet exports keep
one coverage row per expected vote, source and page audits, extracted sections,
vote-to-section links, source-provided vote-to-vote relations, intermediate
vote rows preserving relation IDs, strict model rows, model exclusions, and a
per-vote report. The reproducible 2011–2026 snapshot and artifact hashes are
tracked in `reports/federal_explanations_2011_2026.md`. A missing PDF or failed
page remains visible in the audit.

## Identifier and eligibility rules

The Swissvotes BFS vote number `anr` is mapped by the explicit encoding
`str(int(Decimal(anr) * 10))` to the local OFS `vote_id`. For example,
`554 → 5540` and `682.1 → 6821`. The result must be unique and its voting date
must agree. Raw `anr`, duplicate conversions, non-convertible values, date
mismatches, and Swissvotes entries outside the local 2011–2026 result roster
are audited. Titles are never used to join. Per-field Swissvotes provenance is
kept separate from Chancellery source provenance.

Native PDF text is extracted page by page first. Local Tesseract is called only
for pages without usable native text; OCR output remains technically extracted
but semantically unvalidated. The model export requires a current PDF hash, a
human-confirmed pre-vote decision for that hash, a validated OFS match, explicit
semantic validation, and a non-subsidiary question. Therefore an empty model
export is a valid result until those reviews exist. Correction decisions remain
source-hash bound and contradictory decisions are not applied.

Brochure sections and OFS questions are different units. Several questions can
share one brochure section, and one question may relate to multiple sections;
the source, section, link, and vote tables preserve those relationships.
