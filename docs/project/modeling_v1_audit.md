# V1 preparation audit — 27 October 2026

This is a preparation and provenance audit for issue #58. No model selection or
final-test evaluation was performed.

## Observed coverage

| Population | Observations | Objects | Voting dates |
| --- | ---: | ---: | ---: |
| Retained sources from 2010 onward | 304,616 | 144 | 51 |
| Provisional target window 2012–2025, before eligibility gates | 268,675 | 127 | See machine-readable coverage |
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
