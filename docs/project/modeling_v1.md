# Municipal modeling table V1

The preparation command assembles the candidate features for issue #58. It does
not train a model, select features, or inspect final-test scores. Inputs from
2010 onward supply context; the provisional target window is 2012–2025.

```bash
python3 -m scripts.integration.modeling_v1 \
  --data-root "$PWD/data" \
  --outcomes "$PWD/data/processed/votes_communes.parquet" \
  --geography-id bfs-2026-01-01 \
  --source-version ofs-20260821-e66550d4571a \
  --output /tmp/swiss-voting-v1
```

The geographic reference and version above identify the inspected local OFS PX
snapshot. When replacing that source, verify its metadata and use its actual
reference/version. STATPOP source files and municipal register snapshots are
loaded from `data/raw`; sources are read without modification. Swissvotes bytes
are checked against their provenance sidecar. No download is performed.

Optional `--forecast-evidence` and `--result-evidence` CSV files follow the
documentary evidence contracts in `scripts/integration/modeling_temporal.py`:
one row per `vote_id`, the publication instant, source, exact source version,
and evidence pointer. A voting date, reference year or retrieval timestamp does
not establish historical publication. Optional `--history-config` accepts the
existing `EvaluationConfig` JSON with justified complete-date partitions.
Without it, histories remain unknown and readiness records the missing policy.
No real partition years are chosen automatically.

## Artifacts

| File | Content |
| --- | --- |
| `prepared.parquet` | All retained source observations, canonical candidates, source-block values and provenance |
| `strict_population.parquet` | Target-window rows passing documented eligibility gates |
| `exclusions.csv` | Municipality/object keys, excluded source blocks and reasons |
| `feature_joins.csv` | Per-observation source selection and availability evidence |
| `history_readiness.csv` | History computation statuses, distinct from an established empty history |
| `coverage.json` | Source blocks, objects and voting dates, including candidate missingness |
| `readiness.json` | Strict row counts, unresolved prerequisites and modeling readiness |
| `manifest.json` | Candidate allowlist, input hash, block versions, definitions and configuration |
| `object_join_audit.csv` | Exact OFS–Swissvotes correspondence and consistency checks |
| `unmatched_swissvotes.csv` | Source records outside the OFS coverage or with invalid identifiers |

Rows are ordered by voting date, object and municipality. Identical inputs and
configuration produce identical preparation artifacts. Learned imputation,
encoding, scaling and text vocabularies belong to training folds and are absent
from this stage.

## Data dictionary

The scientific allowlist contains exactly 30 candidates. Canonical columns alias
the explicit source-block columns recorded in the manifest. Counts, target,
identifiers, dates and evidence are retained for audit and cannot expand that
allowlist.

| Candidates | Definition |
| --- | --- |
| `population_total` | Permanent resident population |
| `share_foreign` | Foreign permanent residents / permanent resident population |
| `share_age_0_19`, `share_age_20_39`, `share_age_65_plus` | Age-band population / permanent resident population, after compatible constituent counts are aggregated |
| `canton` | Categorical canton |
| `language_region` | Categorical language region; unavailable classifications remain missing |
| `urban_rural_type` | Categorical urban / intermediate / rural classification |
| `history_yes_mean`, `history_vote_count`, `history_missing` | Equal-object arithmetic mean, count and established-absence indicator over admissible municipal history |
| `history_5y_yes_mean`, `history_5y_vote_count`, `history_5y_missing` | Same summary, restricted to the five calendar years before the forecast instant, lower boundary inclusive |
| `history_same_domain_yes_mean`, `history_same_domain_vote_count`, `history_same_domain_missing` | Same summary for earlier objects sharing at least one admissible broad domain, each counted once |
| `legal_form` | Mandatory referendum, optional referendum, popular initiative or direct counter-proposal |
| `policy_domain_01` … `policy_domain_12` | Deduplicated broad-domain membership; unknown classification remains unknown |

`target_share` is `yes_count / (yes_count + no_count)`, in [0, 1]. Invalid
denominators and ambiguous target/geography remain visible with exclusion
reasons. Ordinary missing optional values do not imply blanket row deletion.
Unknown availability cannot be repaired by imputation.

## Evaluation boundary and limitations

Use the existing `scripts.evaluate_votes.evaluate` boundary with explicit
chronological partitions. Supply original source feature blocks and domain
records, and the complete prepared outcome context as `history_source`.
The evaluator recomputes history with its frozen/rolling policy; persisted
diagnostic history columns must not bypass that calculation. Context before
2012 never becomes estimator-fitting rows. All objects and municipalities on a
voting date remain in the same partition.

The current local source snapshots do not establish historical brochure or
result-publication instants, or historical availability of STATPOP and
classification versions. An empty strict population is an explicit preparation
result, not a forecasting experiment. Retrospective harmonization to 2026
geography is not historical operational geography. Source-block manifests and
readiness retain these distinctions.

Party strength and brochure text are later blocks. Current brochure matching,
semantic validation and exact-version availability are unresolved; existing
text files are not automatically eligible predictors. The independent
[ESPOP audit](../../reports/datasets/espop/audit_1981_2010.md) concerns a possible
extension and does not change this preparation's source floor.
