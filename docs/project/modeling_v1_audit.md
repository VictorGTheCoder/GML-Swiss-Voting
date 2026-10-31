# V1 preparation audit — 27 October 2026

This is a preparation and provenance audit for issue #58. No model selection or
final-test evaluation was performed.

## Observed coverage

| Population | Observations | Objects | Voting dates |
| --- | ---: | ---: | ---: |
| Retained sources from 2010 onward | 304,616 | 144 | 51 |
| Provisional target window 2012–2025, before eligibility gates | 268,675 | 127 | 45 |
| Strict eligible population | 0 | 0 | 0 |

The source contains 1,025,903 outcome rows; 721,287 rows before 2010 are counted
out explicitly. The retained prepared table contains 2,117 distinct geographic
codes, including special political-statistics units that remain audited and
are excluded from modeling. These counts do not imply that all target-window
rows are eligible.

All 30 candidate columns are present. Population, nationality, age and
territorial characteristics have retrospective values for 302,958 retained
observations; 1,658 special-unit observations lack municipal source records.
Swissvotes broad-domain indicators are populated for all retained rows;
legal form remains missing for 4,229 observations outside the four allowed
legal-form categories. Matching uses exact identifiers with independent date
and question-type consistency checks.

The municipal mapping covers all 2,115 source communes and all 2,110 target
communes. Four complete merger groups aggregate demographic counts before
proportions. No source split or missing target is silently allocated. All six
municipal input files and the Swissvotes CSV match their provenance SHA-256
records. The outcome source geography is the OFS PX note's harmonized
2026-01-01 municipal reference.

## Readiness result

Historical brochure publication evidence is absent for every prepared
observation. The current source snapshots also lack documentary evidence for
historical result publication and source-version availability at forecast time.
No source block has an admissible historical match under the strict gate.

The nine histories remain unknown because no justified chronological partition
configuration has been declared. Unknown dates, publication or domains are not
encoded as an established absence of antecedents. The strict population is
empty; no partition boundaries, blanket lags or publication dates were invented.
The evaluator separately recomputes histories under its declared frozen/rolling
policy and skips the additional history model when active rows have unresolved
history availability.

The exclusion log is a long audit table: one observation may have several
reasons and several unavailable source blocks. Its reason totals must not be
summed to infer unique excluded observations.

## Reproduction and retained evidence

The [preparation guide](modeling_v1.md) gives the command, dictionary and
evaluator boundary. The [curated prepared snapshot](../../data/processed/modeling_v1/README.md)
versions the table, empty strict population, manifest, coverage and readiness.
Full row-level reports and reloadable source blocks are generated locally under
`reports/modeling/v1` by the same command. Source files remain unchanged.

Synthetic tests establish target calculation, joins, temporal gates, history
policies, deterministic artifacts and evaluator compatibility. They do not
establish missing historical publication facts or empirical predictive gains.
Party strength and brochure text remain later blocks. ESPOP extension work
remains independent of this STATPOP-era V1.

## Integration audit — 31 October 2026

The integration branch starts from `main` at `6fd4666` and merges the V1 tip
`e6658de`. The sections above record the original branch's raw-source audit.
The curated snapshot is now rebuilt from main's established source Parquets;
its manifest records those exact bytes instead of requiring absent local CSVs.
The source tables and the separate exploratory modeling table are preserved.

Research covered #58–#60, #62–#67, their implementation comments, merged PRs
#55/#57 and the project contracts/journal. Main already contained the ESPOP
feasibility audit, newer data pipelines, module reorganization, expanding-window
model evaluation, combined ablations and boosting. The integration preserves
those components and the newer documentation/CI. V1 imports move to
`scripts.modeling` and `scripts.repertoire_communes`. The independent #67
prototype remains independent and does not extend the main study period.

The new default adapter reads the already harmonized STATPOP and territorial
snapshots, hashes them, maps their explicit feature names, and marks publication
availability unknown. It ignores the exploratory `available_from` assumption.
No scientific decision changed: retrospective common geography and unknown
historical availability remain separate. Canonical V1 municipality identifiers
are normalized decimal strings; source files retain their four-character IDs.
The legacy adapter and its complete-merger behavior remain available and tested.

Rebuilt coverage matches the original audit: **304,616 rows, 144 objects, 51 dates**;
**268,675 rows, 127 objects, 45 dates** in 2012–2025 before gates; **0 strict rows**.
The OFS source SHA-256 is
`231bc1806c6cfd2050795265d973d6c512211e8fb82e0a5a6c6e715348325207`.
All 511 source OFS objects match Swissvotes exactly, with dates and question
types checked. Of the retained rows, 302,958 have municipal values and 300,387
have one of the four allowed legal forms. No real model was fitted or scored.

Integration fixes keep the baseline missing-history flag distinct from the V1
flag in Ridge, boosting and text paths; preserve main's windowed fits and
combined models; and record a skipped V1 family when new final-period evidence
is unresolved. Validation skips remain skipped after freezing. ISO dates retain
year-month-day semantics even when original Swissvotes CSV dates require
French day-first parsing. History partition assignment owns mutable storage
for compatibility with pandas 3. No dependency additions were required.

Local verification uses Python 3.12.3 with the repository's `requirements-test.txt`
installed in `.venv` via `uv` (system `python`/pip were unavailable):

- `python -m pytest tests -q`: **254 passed**. The synthetic V1 CLI export/reload
  check also passes and keeps the test date out of validation predictions.
- `python -m ruff check scripts tests` and `git diff --check`: pass.
- `python -m scripts.integration.audit_datasets`: **PASS_WITH_LIMITATIONS**, no
  structural errors. All 2,105 ordinary OFS municipality IDs match communal
  sources; historical territory/publication and brochure validation limits remain.
- Two full V1 preparation runs use the documented command and the local prepared
  source tables. All **15 exported files are byte-identical**, including row-level audits,
  Parquets and source block descriptors. Target/key/allowlist checks and all
  source hashes pass; the five curated files were promoted from that run.

No raw source download, OCR rerun or independent real ESPOP prototype execution
was performed: their local raw inputs are absent. Source snapshots are available,
so the complete main-layout V1 preparation runs without those inputs or credentials.
The evaluator's API and CLI accept the exported feature/domain/history artifacts;
synthetic compatibility does not establish real forecast readiness. Old frozen
experiments must be revalidated because implementation hashes have changed.

Follow-up remains documentary: obtain version-bound brochure/result/source release
evidence, audit strict coverage, then justify complete-date partitions. Party
features, text contributions and any ESPOP extension require their existing
separate gates. Human PR review and remote CI remain distinct from local tests.

The first integration CI run
[41199789865](https://github.com/VictorGTheCoder/GML-Swiss-Voting/actions/runs/41199789865)
failed on both operating systems before dependency installation: the existing
`setup-python` pip cache searched for `requirements.txt`/`pyproject.toml`, while
the repository uses `requirements-test.txt`. The workflow now explicitly sets
`cache-dependency-path: requirements-test.txt`; this preserves its original
Windows/Linux matrix and commands. Those failed jobs did not run tests.
