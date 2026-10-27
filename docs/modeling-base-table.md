# Prepared municipal voting table foundation

Run `python -m scripts.integration.prepare_modeling --geography-id <verified-reference>
--source-version <input-version>` after the OFS municipal cleaning pipeline.
The command writes
`data/processed/modeling/prepared_municipal_voting_base.parquet` and
`reports/modeling/base_preparation.json`. It leaves its input parquet unchanged.

The preparation API is `prepare_base_table(outcomes, *, geography_id,
source_version, geography_crosswalk=None)`. It returns a `BasePreparation`
with the prepared table, grouped preparation-status counts, join checks, and
coverage counts. Inputs use the cleaned OFS field names. A geography crosswalk
must have one row per source municipality and declare its target identifier,
mapping type, version, and evidence. Unchanged, recoded, and explicitly
complete merge mappings can be used. Merge counts are summed before the yes
share is recalculated. Splits, missing links, and ambiguous source links remain
visible with exclusion statuses.

Rows retain `municipality_id`, `vote_id`, `voting_date`, yes/no counts, and
`target_share = yes_count / (yes_count + no_count)`. The source floor defaults
to 2010, as requested for the current STATPOP-era scope; earlier dated rows are
counted in the coverage report and omitted from the run. Results from 2010
onward remain available for later historical features; `target_period_eligible`
marks the provisional 2012–2025 target window. The main target period is not
expanded to include 2026. The identifier pair is checked for duplicates after
geographic mapping. Multiple objects on one date remain separate by `vote_id`.

The table also carries the evaluation contract's required columns for
forecast/result availability, geography, and population flags. Publication
proofs are explicitly unknown at this base stage; later temporal preparation
must populate them. Therefore `ready_for_enrichment` is not a claim of strict
modeling eligibility. Invalid targets, duplicate keys, special units,
subsidiary questions, provisional results, and unresolved geography have
separate statuses and remain in the audit output. Ordinary missing predictor
values are not dropped.

`source_version` and `geography_id` must be supplied by the real-data
orchestrator from verified provenance. The preparation step does not infer
either value from current file contents. Do not treat the base output as a
strict modeling population until temporal and geographic eligibility are
resolved.
