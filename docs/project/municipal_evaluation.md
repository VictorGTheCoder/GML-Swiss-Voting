# Publication-aware municipal evaluation

The public integration boundary is `scripts.evaluate_votes.evaluate(prepared, EvaluationConfig)`.
It runs independently of communal and brochure-text sources. The testing seam is the complete
orchestrator using synthetic prepared records, as agreed in issue #33.

```bash
python3 -m scripts.evaluate_votes --synthetic --output /tmp/swiss-voting-synthetic
python3 -m pytest -q tests/test_evaluate_votes.py
```

The illustrative dataset predicts 40% for the constant baseline. Municipal history predicts 20%
for municipality `a` and falls back to 40% for new municipality `c`. Validation targets are 80%
and 40%; respective equal-row MAEs are 20 and 30 percentage points. The final 2022 date stays
reserved. Synthetic evidence is illustrative and makes no historical Swiss availability claim.

## Prepared contract

One row represents municipality × voting object. Municipality and vote identifiers are strings.
The orchestrator copies inputs and never reads arbitrary numerical columns as predictors.

| Column | Meaning |
| --- | --- |
| `municipality_id`, `vote_id` | Stable string keys; preserve leading zeros during ingestion |
| `voting_date` | Whole date, normalized to UTC; one date per object |
| `yes_count`, `no_count` | Nonnegative finite counts; target is yes/(yes+no), in [0,1] |
| `geography_id` | Comparable territorial reference, not merely municipality identifier |
| `source_version` | Identifies the prepared outcome source/version |
| `forecast_at`, `forecast_evidence` | Actual brochure-publication instant and documentary evidence pointer; one instant per object |
| `result_available_at`, `result_availability_evidence` | Historical outcome publication instant and evidence pointer; unknown values cannot enter history |
| `is_special_unit`, `is_subsidiary`, `is_provisional` | Explicit boolean modeling eligibility flags |
| `flag_*` (optional) | Additional preparation audit flags; true or unknown values are excluded and counted individually |
| `evaluation_weight` (optional) | Retrospective electorate count used only for complementary evaluation; never a predictor |

Undefined targets, every instance of duplicate keys, missing identifiers/geography/source version,
ambiguous eligibility flags, provisional/special/subsidiary rows, missing forecast evidence and
forecasts at/after voting are excluded with sequential reason counts. Additional `flag_*` columns
are handled by the explicit `audit_flag_policy='exclude'`; adapt upstream audit flags to boolean
columns. Reasons count the first applicable exclusion; rows are not counted twice. Inconsistent
object dates or forecast instants raise an error. Cleaners remain unchanged.

The evaluation accepts a prepared geographical reference. Equality of `geography_id` is required
for municipal history. It does not establish crosswalk validity; prepared-source integration must
validate that separately. `geography_mode='historically_existing'` records a historical operational
claim by the preparer; `retrospective_fixed` identifies harmonized retrospective geography and
must not be reported as historical territorial availability.

## Experiment configuration and leakage policy

`EvaluationConfig` declares nonempty `train_dates`, `validation_dates`, and `test_dates` as lists or
tuples of ISO dates. Dates must be unique, disjoint, and chronological. Every object and municipality
on a declared date receives the same partition; undeclared dates are excluded. Exact real boundaries
must be established from verified coverage before tuning. Missing eligible partitions are reported
rather than populated with invented rows.

`history_policy='frozen'` restricts municipal history to training rows. `rolling` additionally admits
earlier validation outcomes for subsequent predictions. Both require an earlier voting date and
result publication evidence at or before the individual forecast instant. Unknown or late publication
never enters either baseline. Same-date results are excluded even for multiple objects.

The constant is the equal-row mean of admissible training targets at the forecast cutoff. Municipal
history is the equal-row mean of admissible, geographically comparable municipal targets. Its
fallback always uses the training-only constant, including in rolling mode. Where no admissible
training target exists, both models abstain; `no_admissible_training_history` and
`coverage.unpredictable_rows` explain the loss. `coverage.municipal_history` reports fallback rows
and fraction. The allowlist is exactly `municipal_history`, `history_missing`; arbitrary outcome,
turnout, ballot-total and electorate fields cannot become predictors.

Ordinary `mode='validation'` runs emit no test predictions or scores. Explicit
`mode='final_test', choices_frozen=True` is required after model choices are frozen. Baseline
training remains the declared training period; a later trained model must explicitly document any
training-plus-validation refit. `seed` is recorded although these baselines use no randomness.

## Artifacts and extensions

The return dictionary contains DataFrames `eligible_rows`, `partitions`, long `predictions`,
`by_object`, and `by_date`, and dictionaries `manifest`, `coverage`, `exclusions`, and `metrics`.
Eligible rows add `target_share` and `partition`; dates are timezone-aware UTC. Predictions add
`model` (`constant` or `municipal_history`), `prediction` (share), and `fallback` (boolean).
Metrics report equal-row `mae_pp`, `electorate_weighted_mae_pp` and weight coverage. Invalid,
missing or nonpositive weights are omitted only from the weighted score. Weight provenance must
be provided by the prepared source and is independent of predictor availability.

The manifest records source versions, exact input JSON-content hash, library versions,
configuration, forecast cutoffs, allowlist, policy and geography mode. Input hashing preserves row
order and column order; identical inputs/configurations reproduce outputs. CLI artifacts serialize
DataFrames as CSV and the remaining dictionaries as `summary.json`; `write_artifacts` works for
later source-block and text evaluations using this same result structure. Additional model families
should consume only explicitly admissible features and preserve identical comparison keys.

Real prepared runs use `--input prepared.csv --config experiment.json --output /tmp/run` (Parquet
also supported). The local `data/processed/votes_communes.parquet` is **not yet forecast-ready**:
it needs explicit per-object evidenced brochure publication, historical result publication/version
availability, and verified geographical references/crosswalks. Its `vote_date`, `votes_yes`,
`votes_no`, and `is_tiebreak_question` names also need an explicit adapter to the contract above.
No publication instants are fabricated from voting dates. Missing columns are reported by name;
no real strict-forecast score is claimed until these prerequisites exist.

## Previous work inspected

`victor-temp` contains `scripts/evaluate_baselines.py`, its tests and
`docs/project/baseline_protocol.md`. That implementation explicitly describes retrospective fixed
2026 geography, with no verified forecast or result-publication evidence. It therefore cannot be
cherry-picked as a strict forecast pipeline. This implementation reuses its verified concepts:
yes/no count-derived shares, complete-date chronological partitions, municipal mean with a
training-only fallback, percentage-point MAE, and reserved test policy. Publication gating,
explicit evidence, auditable eligibility and configurable rolling history require reconstruction.
`victor`, `origin/victor` and `origin/exploration` were also inspected for baseline artifacts;
source research is retained outside the repository by the integration task. Previous retrospective
scores are not re-labelled as forecast scores.
