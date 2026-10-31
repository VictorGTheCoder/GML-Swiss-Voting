# Prepared municipal voting table

The preparation boundary is `scripts.integration.modeling_temporal.prepare_modeling_table`.
It combines the cleaned OFS commune results with per-object forecast and result
publication evidence, then returns both the complete prepared table and its
strictly eligible population. It does not fit a model or choose date partitions.

Run with explicit evidence files when available:

```bash
python3 -m scripts.integration.modeling_temporal \
  --input data/processed/ofs-votes/votes_communes.parquet \
  --forecast-evidence data/raw/modeling/brochure_publications.csv \
  --result-evidence data/raw/modeling/result_publications.csv \
  --blocks data/raw/modeling/feature_blocks.json \
  --geography-id 'BFS commune register 2026-01-01' \
  --source-version 'OFS PX px-x-1703030000_101; retrieved 2026-09-29'
```

`--blocks` is optional until prepared source blocks are available.

The forecast CSV has `vote_id`, `forecast_at`, `forecast_source`,
`forecast_source_version`, and `forecast_evidence`. Its instant must be the
official brochure publication time. The source and source version identify the
release, and evidence points to the record that establishes that time. The
result CSV has `vote_id`, `result_available_at`, `result_source`,
`result_source_version`, and `result_availability_evidence`. These
records describe when a result may be used as later voting history; a target's
own result need not have been available at its forecast instant.

Missing evidence stays null in the prepared table and receives an `unknown`
status. A forecast at or after voting is invalid. A claimed result publication
before voting is retained as `reported_result_available_at` for audit, while
the canonical history availability instant is cleared so it cannot enter a
history calculation. No publication date is inferred from voting dates or the
current retrieval time.

The source floor defaults to 2010, matching the user's confirmed STATPOP-era
scope. Target observations remain provisionally 2012–2025. Earlier rows from
2010 onward remain prepared as possible history; rows before the source floor
are counted in the readiness report. Target-period boundaries and all-date
partitions are not inferred from source coverage.

When a feature has values in a current retrospective source but its publication
time is unknown or late, the prepared table retains those values with separate
`<block>__availability_status`, `<block>__source_version`, reference/publication
times and evidence columns. Such values are explicitly retrospective and are
not selected into the strict population. An as-of matched release instead uses
the latest source/reference version evidenced by the forecast cutoff.

The strict population requires a valid target, ordinary principal observation,
usable geography, and evidenced forecast before voting. Ordinary predictor
missingness does not remove a row. When a feature block is supplied, unknown or
late availability and incompatible geography exclude its rows from the strict
population; the per-row feature report keeps its block, municipality, object,
and status. A missing entity remains ordinary missingness. The evaluator's
`evaluate` function consumes the strict rows using its existing date and
history policies.

By default geography is `retrospective_fixed` on the 2026-01-01 commune
register, the reference declared by the OFS vote cube. This records a retrospective
common geography, not the municipal boundaries available at each historical
forecast. `historically_existing` additionally checks mapping publication and
territorial validity instants where a crosswalk is supplied.

The command writes `prepared_municipal_voting.parquet`,
`strict_modeling_population.parquet`, `temporal_readiness.json`,
`temporal_exclusions.csv`, and `feature_availability.csv` beneath the configured
output paths. An empty strict population is reported as `strict_population_empty`;
it is a readiness result and produces no model score.
