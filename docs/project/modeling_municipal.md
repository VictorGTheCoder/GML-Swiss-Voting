# Municipal features for modeling V1

`prepare_municipal_table` in `scripts.integration.modeling_municipal` enriches the
complete prepared municipal voting table. Its `MunicipalPreparation` result
retains the temporal preparation, source audit and reusable feature blocks.
`build_municipal_feature_blocks` exposes the same adapters for assembly with
other feature blocks. No encoding, imputation or standardization is fitted.

The eight allowlisted candidates are permanent resident `population_total`,
`share_foreign`, `share_age_0_19`, `share_age_20_39`, `share_age_65_plus`, and the
nominal categories `canton`, `language_region`, `urban_rural_type`. Age counts
use five-year lower bounds 0/5/10/15, 20/25/30/35 and 65 through 100+ respectively.
Every denominator is total permanent resident population. The 40–64 share and
detailed 9/25-class typologies are excluded.

BFS `STALAN2020` supplies urban/intermediate/rural codes 1/2/3;
`SPRGEB2020` supplies language-region codes. `REGCH` and `DEGURB2021` are
separate classifications and are excluded. Categories remain nominal strings.
The current classification export is anchored to its declared 2026-01-01
geographic reference; its field names alone do not prove historical publication.

Municipality codes are explicitly normalized before cardinality-checked joins.
The register adapter resolves the 2025-04-06 source snapshot through documented
mutations to the 2026-01-01 target snapshot. Unsupported splits remain unresolved.
Counts are summed across every expected merger constituent before dividing.
Missing constituents, suppressed/non-numeric/negative counts, incomplete selected
age bins and inconsistent complete age vectors produce missing values, not zero.
Aggregate 8100 is excluded. Duplicate source keys or ambiguous mappings fail.
Source-year coverage and unmatched identifiers remain in the audit.

STATPOP sources are restricted to 2010–2025; target eligibility remains 2012–2025
in the base preparation. Ordinary predictor missingness preserves prepared rows.
The temporal layer records missing indicators, per-object/date coverage and
join statuses independently of the strict population. Version-specific evidence
must contain an exact `source_version`, publication timestamp and documentary
evidence. Population/age evidence is keyed by year and source commune; territory
evidence by target commune. A merger inherits the latest publication only when
all constituents have proof. Unknown or late availability blocks strict use while
retaining retrospective values. Current retrieval or approximate release dates
are never used as historical availability evidence.

`load_local_municipal_sources(Path(".../data/raw"))` reads sources without edits.
The CLI additionally accepts outcomes, optional forecast/result evidence and
explicit output paths. Current local sources have no documentary historical
publication evidence; strict municipal-feature availability remains unresolved.
Feature definitions and provenance are exported in `audit.feature_manifests`;
coverage is exported in `audit.feature_coverage`. Full temporal artifacts can be
written with `modeling_temporal.write_modeling_artifacts(result.preparation)`.
