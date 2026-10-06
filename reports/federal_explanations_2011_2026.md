# Federal explanations audit, French, 2011–2026

**Audit run:** 2026-10-06. **Scope:** every unique vote question in the
read-only OFS communal results reference dated 2011-02-13 through 2026-06-14,
matched to the French Federal Chancellery archive. **LLM budget:** 0 CHF.

## Results

| Check | Result |
|---|---:|
| Expected OFS vote questions | 136 |
| Swissvotes `anr` to OFS vote IDs, exact encoded join and date check | 136 / 136 |
| Duplicate / invalid / in-period unmatched Swissvotes IDs | 0 / 0 / 0 |
| Swissvotes rows before local result period / after latest local result | 572 / 6 |
| Official Chancellery PDFs cached | 48 |
| PDF pages | 2,459 |
| Native text pages | 2,435 |
| Local French OCR fallback pages, successful / failed | 24 / 0 |
| Parsed brochure sections | 137 |
| Sections with extracted official summary | 127 / 137 |
| Sections with authority recommendation text (both authority fields) | 128 / 137 |
| Parsed recommendation target/position/type | 123 clear single-target; 5 ambiguous or unclear; 9 not extracted |
| Candidate section-to-vote links, all unresolved pending review | 444 |
| Source-provided vote-to-vote relation edges | 0 (OFS input has no relation IDs) |
| Model-eligible rows | 0 |

Swissvotes uses a numeric BFS number, while the local OFS key encodes tenths.
The verified conversion is `str(int(Decimal(anr) * 10))`: for example,
`554 → 5540` and `682.1 → 6821`. Every converted key was unique and its vote
date matched. The raw `anr` value is retained. Swissvotes contains 572 historical
rows before this local result period and six future rows after the latest local
result (2026-06-14); these are separately reported in the join audit.
The six future normalized IDs are `6880`, `6890`, `6900`, `6910`, `6920`, and
`6930`.

The 48 archive PDFs cover all expected vote dates. Native PDF text was available
on 2,435 pages. The other 24 pages were passed to local Tesseract 4.1.1 with the
French `fra.traineddata` model; all 24 produced technical OCR output. OCR output
remains semantically unvalidated. `pages.parquet` records method, page, status,
error, and semantic status per page.

The expected vote-question count and parsed-section count differ on three
dates. These counts use different units, so they do not establish missing text
or an automatic link:

| Vote date | OFS vote IDs | Questions | Sections | Audit interpretation |
|---|---|---:|---:|---|
| 2012-11-25 | `5660` | 1 | 5 | Four additional brochure sections have no corresponding local OFS question; their relation remains unresolved. |
| 2018-03-04 | `6160`, `6170` | 2 | 1 | One section may cover related questions; explicit mapping is unresolved. |
| 2026-03-08 | `6821`, `6822`, `6823`, `6830`, `6840`, `6850` | 6 | 4 | Linked proposal and subsidiary questions can share sections; explicit mapping is unresolved. |

No expected OFS row has zero sections in its date-associated brochure. However,
**all 444 candidate links remain `UNRESOLVED`**: grouping by ballot date is only
a discovery aid and does not prove which section explains which question. The
48 source records also have no qualifying version-bound pre-vote review.
Automated extraction and OCR do not establish semantic correctness. These
three review gates keep the model export empty: confirmed pre-vote availability
for the exact PDF hash, validated section-to-OFS correspondence, and explicit
semantic validation. Subsidiary questions are also excluded.

Swissvotes contributes structured titles, legal-form codes, topic codes, and
authority positions with per-field provenance. It does not supply the
Chancellery brochure summary, arguments, or explanatory text; those remain
derived from the official PDF. Structured campaign arguments are deferred.

The full-period section export now includes `summary_official` and its missing
reason, each authority's raw recommendation, parsed action (`position`),
target type, and parser reason. Of 137 sections, 127 have a detected summary;
128 have a detected authority recommendation. Among council recommendation
fields, 123 parse to one target, five remain ambiguous or unclear, and nine
were not extracted. Recommendation types such as `INITIATIVE` and `QUESTION`
describe the parser's target classification; they do not validate the source
text. `related_votes.parquet` is an empty two-column edge table because the
read-only OFS input contains no `related_vote_ids`; `votes_intermediate.parquet`
preserves the input relation lists (empty for these 136 rows). The pipeline
does not infer relations from shared vote dates or brochure content.

## Sources and provenance

- OFS reference: `data/processed/votes_communes.parquet`, SHA-256
  `8abd2775d8a8ade51b79c4e427d67e25511d77be7d2426728eaf776ca2f0e836`.
- Swissvotes release: **DATASET CSV 28-09-2026**, acquired 2026-10-06; delimiter
  `;`; license **CC BY 4.0**; source page and download URL are recorded in
  `artifacts/source_provenance.json`; CSV SHA-256
  `594dbafb5c9ae8f7563f1e0e3de00cac561993cdfd53034e86ed8bce1ddc3a35`.
- Chancellery archive: [Compilation des explications du Conseil fédéral depuis
  1978](https://www.bk.admin.ch/fr/compilation-des-explications-du-conseil-federal-depuis-1978).
  Each official PDF URL, vote date, collection timestamp, and PDF SHA-256 is in
  `artifacts/sources.parquet`. Collection time is not treated as publication
  time. Raw PDFs are retained in the local content-addressed cache and are not
  committed.
- Tesseract `fra.traineddata` from
  [tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast/blob/main/fra.traineddata),
  SHA-256 `ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca`.

## Review artifacts

Parquet outputs from this run are committed under `reports/federal_explanations/artifacts/`.
SHA-256 hashes:

| Artifact | SHA-256 |
|---|---|
| `coverage.parquet` | `e163b5d2f39c26ed0ac49e6875327ac06266342248278da76e52e41881df0320` |
| `sources.parquet` | `6b6176e4d09431a463e37f9e344e7ae895d348bf5373ebf220c24e38cca9785b` |
| `pages.parquet` | `5b8b9c06e5f67822823ec37f0c75106167ff7ca257f664960d409b165e72996f` |
| `sections.parquet` | `5eff1efa9d0f94f3ddb9d6cbecd7d3e3f99557f4a24eae90eb4f415d05b95d58` |
| `section_links.parquet` | `d938c30663fcc5b2699ac44251543a2e5119f0793bc9eb519257979ed3642433` |
| `related_votes.parquet` | `4df5c24a939917f33c5fd80e4a9a4e173d9153e0f2b481658f28a4e981d17ee2` |
| `votes_intermediate.parquet` | `919d45655f2ce24cde90284a58a5e45991affb5b923b61e5403b51f7c50d5dc2` |
| `document_audit.parquet` | `67191d40152cc655d675cf40de5de631cc940b022c7168d7aa2e64f6b03b46fe` |
| `model.parquet` | `d5d43c89560dfd381902292e0bd746902176676e6e62e5266c08582ce281e630` |
| `model_exclusions.parquet` | `a6bf27ba450f2a42b291a6370355d4f70cecae1c74aeb4f3aaa26914ee2ad228` |
| `audit_report.md` | `89354efef64a16be03fc98732bd22a16d7c6533c7b5bed946e033c9c613694af` |

Reproduction and offline replay instructions are in
[`docs/federal_explanations_full_audit.md`](../../docs/federal_explanations_full_audit.md).
