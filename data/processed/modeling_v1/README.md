# Audited municipal preparation V1

This snapshot is a **prepared municipal voting table**, including observations
awaiting evidence. It is not an eligible forecasting dataset.

- Sources/history scope: 2010 onward; provisional target window: 2012–2025.
- Geography: retrospective harmonized BFS municipality reference 2026-01-01.
- Prepared observations: 304,616 municipality–object rows, 144 objects, 51 dates.
- Target-window observations before eligibility gates: 268,675 rows, 127 objects.
- Strict population: **0 rows**. Brochure publication, result publication and
  source-vintage availability evidence are missing. Chronological partitions
  and history policy remain undeclared. No final-test score was computed.

All 30 candidate columns are present. The nine history values remain unknown
until a justified configuration and admissible historical evidence are supplied.
Retrospective municipal and object values retain explicit availability statuses;
they must not be treated as historically available predictors.

`manifest.json` pins input/configuration and feature-block provenance;
`coverage.json` and `readiness.json` explain coverage and exclusions. The integration snapshot uses main's prepared source tables, whose exact byte hashes
are recorded in `manifest.json` (`source_audit`). Historical release evidence
remains unknown; exploratory `available_from` is not promoted to publication
proof. The original raw adapter separately verifies its provenance sidecars.
Full row-level logs and reloadable feature blocks are generated under
`reports/generated/modeling_v1`;
they are not versioned here.

Reproduce the complete bundle using the command in
[the preparation guide](../../../docs/project/modeling_v1.md), with output
`reports/generated/modeling_v1`, then copy its five curated artifacts (`prepared.parquet`,
`strict_population.parquet`, `manifest.json`, `coverage.json`, `readiness.json`)
to this directory. Consult the manifest for the exact required source versions.
Replacing source files requires a new audited snapshot; do not invent missing
publication evidence or infer it from retrieval dates.
