# Swissvotes object feature block

`scripts.integration.modeling_objects` produces the 13 candidate object features
for the prepared municipal voting table: categorical `legal_form` and the
numeric indicators `policy_domain_01` through `policy_domain_12`. It does not
copy other numeric columns from Swissvotes into the predictor set.

The public adapter is `build_object_feature_block(ofs_objects, swissvotes,
source_version=..., source_url=...)`. It accepts the canonical OFS object
identity, voting date and subsidiary-question flag, plus the Swissvotes fields
`anr`, `datum`, `rechtsform` and `d1e1`, `d2e1`, `d3e1`. `swissvotes_key`
converts `anr` to the OFS key with decimal arithmetic. The adapter joins on that
key only; date and question type are separate integrity checks. Duplicate,
unmatched, invalid and conflicting keys remain in `join_audit` or
`unmatched_swissvotes` and do not multiply municipal rows.

Legal forms 1–4 are named categories: mandatory referendum, optional
referendum, popular initiative and direct counterproposal. Code 5 is a
subsidiary question; it is represented as missing `legal_form` and the existing
OFS eligibility flag keeps it out of the strict population.

Broad domains are the deduplicated set of valid integer codes 1–12 among
`d1e1`, `d2e1` and `d3e1`. A dot or blank means that optional slot is empty.
When no valid broad domain can be established, all 12 indicators and the domain
set remain missing with `domain_status=unknown_classification`; they are not
treated as a known set of zero domains. Fine levels `e2` and `e3` are not used.
The [Swissvotes codebook](https://swissvotes.ch/page/dataset/codebook-en.pdf)
describes the legal forms and broad policy domains in sections on pages 3–10.

`ObjectFeaturePreparation.feature_block` is suitable for the complete
`prepare_modeling_table` seam. `domain_metadata` preserves one row per object,
the domain set and status, exact-match evidence, source version and temporal
availability fields so history preparation can independently check whether a
domain classification was available at a target forecast instant. Matched
values from a current retrospective file remain in the prepared table even when
publication evidence is unknown; the temporal gate excludes them from strict
use. This project's current Swissvotes file was retrieved on 2026-10-06, and
that retrieval timestamp does not establish historical publication.

To read the checked local comma-separated source and sidecar, call
`load_swissvotes_source(data_root)` where `data_root` contains
`raw/features/swissvotes_dataset.csv` and
`raw/features/swissvotes_dataset.provenance.json`. The loader checks the file
SHA-256 against the sidecar and returns it as the source version. It performs no
download. Provide independently evidenced per-object metadata availability via
`publication_records` when such records exist; otherwise availability remains
unknown.

The tests exercise complete municipal-table construction with multiple objects
on one date, a multi-domain object, a subsidiary question, unknown
classification, identifier mismatch and a duplicate Swissvotes key. The
prepared block contains only the declared 13 predictors; national and canton
outcomes, turnout, titles and other metadata are excluded.
