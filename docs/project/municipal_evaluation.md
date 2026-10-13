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
| `voting_date` | Whole UTC calendar date; timestamps normalize to midnight before partition checks; one date per object |
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
tuples of ISO dates. Voting timestamps are normalized to whole UTC calendar dates before checks,
so different instants on the same voting day cannot cross partitions. Dates must be unique, disjoint, and chronological. Every object and municipality
on a declared date receives the same partition; undeclared dates are excluded. Exact real boundaries
must be established from verified coverage before tuning. Missing eligible partitions are reported
rather than populated with invented rows.

`validation_windows` may split `validation_dates` into nonempty chronological groups. Every
validation date must appear exactly once; each window keeps complete dates together. If omitted,
the declared validation dates form one window for backward compatibility. Ridge uses an expanding
fit pool: the initial training dates plus earlier validation windows whose outcomes are published
by the first forecast instant in the current window. The reserved test remains disjoint and is never
scored during validation.

`history_policy='frozen'` restricts municipal history to training rows. `rolling` additionally admits
earlier held-out outcomes for subsequent predictions, including earlier test dates in an explicit final run. Both require an earlier voting date and
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

## Geography crosswalks (#35)

Pass an optional `geography_crosswalk` DataFrame to the same `evaluate` seam, or use
`--crosswalk crosswalk.csv` in the CLI. Each row declares `source_municipality_id`,
`source_geography_id`, `target_municipality_id`, `target_geography_id`, `mapping_type`,
`crosswalk_version`, `crosswalk_evidence`, `mapping_available_at`, and `target_valid_from`.
Optional `target_valid_to` is an exclusive end instant. Identifiers and reference states are strings;
all times are normalized to UTC. Evidence is an auditable documentary pointer supplied by the
preparer; the evaluator does not infer territorial history from numeric municipality codes.

Supported mapping types are `identity` between different reference states and `merger`. A source
may have only one supported destination. Explicit `split` rows (including multiple destinations)
and other unsupported mapping types exclude the source observation once. Duplicate mapping rows,
ambiguous supported source cardinality, inconsistent target lifetimes, and many-to-one mappings
without an explicit merger raise errors. Source-reference rows without a mapping are excluded
rather than assumed compatible. References not involved in a crosswalk remain prepared identities.

For each merger and object, all declared constituents must be present after eligibility checks.
An incomplete merger excludes the remaining constituents; it cannot silently redefine the target
territory. Supported mergers sum **yes and no counts before computing the target share**. For
example, 20 yes/80 no plus 90 yes/210 no becomes 110 yes/290 no = 27.5%, rather than the
unweighted average of 20% and 30%. Electorate evaluation weights are also summed, only when all
constituent weights are valid. Result availability is the latest constituent publication; any missing
publication instant or evidence leaves aggregate history unavailable. Source versions, evidence,
and constituent municipality IDs are retained. Already-target rows overlapping mapped constituents
raise an error; no prepared result can be counted twice.

`historically_existing` conservatively requires mapping publication no later than each row's
forecast instant and target existence at that instant (`valid_from <= forecast < valid_to`). It
excludes future, unknown, or abolished target states with explicit reasons. This conservative
preparation policy may discard historical merger records whose territorial mapping became known
only later; they do not silently reappear in the global fallback. `retrospective_fixed` permits a
later mapping/reference state for retrospective analysis, labels that mode in the manifest, and
still requires crosswalk version/evidence and historical **result** publication cutoffs. It does not
claim historical operational geography.

Outputs add `source_municipalities`, `harmonization_applied`, `crosswalk_version`, and
`crosswalk_evidence` for mapped rows. The manifest's `geography` block lists input/output reference
states, crosswalk versions, documentary evidence, the exact crosswalk content hash, and the mode.
Prepared harmonized rows can be evaluated without another crosswalk only when their provenance
is retained. Attempting to map a row with `harmonization_applied=True` again raises an error.
Geography exclusions appear alongside other eligibility exclusions; fallback coverage and baseline
errors are calculated only after these checks.

## Prepared communal blocks and regularized references (#36)

```bash
python3 -m scripts.evaluate_votes --synthetic --synthetic-features --output /tmp/swiss-voting-features
python3 -m pytest -q tests/test_evaluate_features.py
```

This remains the same evaluation entry point. It adds an explicitly illustrative STATPOP fixture
and compares `ridge_history` with `ridge_statpop_nationality` on the same validation keys as both
baselines. A source block is not required to improve error. These small synthetic scores establish
reproducibility, not Swiss predictive performance.

`evaluate(..., feature_blocks=(FeatureBlock(...),))` accepts `scripts.feature_blocks.FeatureBlock`:
`block_id`, `scope` (`municipality` or `object`), `records` (DataFrame), `numeric_features`,
`categorical_features`, `definitions`, `source_url`, `source_version`, and `geography_mode`.
All features need documented definitions/units; allowlists are the only columns supplied to a
model. Known same-object outcome and target fields are rejected. Each block creates one independent
reference (`ridge_<block_id>`), plus the history-only regularized comparator; multiple blocks are
not silently pooled into an unexplained combined experiment.

Prepared feature records carry their scope's `municipality_id` or `vote_id`, `reference_date`,
`published_at`, `availability_status='verified'`, `availability_evidence`, `source_version`, and
allowed values. Municipality blocks also require `geography_id`. Record source versions must agree
with the block version. Statistical reference date is distinct from publication date. A value is
admissible only when both are no later than its object's forecast and publication evidence is
verified/nonempty. Municipal geography reference and experiment mode must agree. Most recent
admissible publication wins, breaking same-publication ties by reference date. Duplicate entity ×
reference × publication × geography release keys raise an error; joins retain one observation row.

Unavailable sources do not remove an otherwise eligible voting target. `joined_features` contains
allowlisted, namespaced columns (`<block_id>__<feature>`) and historical predictors. `join_report`
records each block/observation's status and, for matches, the selected reference date, publication
and evidence. Coverage records missing entity, unknown availability, unavailable-at-forecast,
incompatible-geography and matched rows, plus per-feature missing-value counts. Nonfinite numeric
values become explicit missingness. A block with no admissible matches is labelled
`no_admissible_matches`; its reference contains no communal information and cannot support an
incremental source-value claim. Its history-only comparator remains usable.

### STATPOP nationality adapter and real prerequisites

The existing teammates' `data/raw/features/statpop_nationality.csv` is the selected prepared source:
`year`, `code`, `population`, and `foreign`. Its population definition is permanent resident
population; `foreign_share` is foreign permanent residents divided by total permanent residents.
`prepare_statpop_nationality(frame, source_version=..., geography_id=..., source_url=...,
publication_evidence=..., geography_mode=...)` adapts this table without downloading or rebuilding
collection. Read `code` as a string to retain leading zeros. Nonpositive/nonfinite populations,
negative foreign counts or foreign counts exceeding the population yield missing feature values.
The annual statistical reference is 31 December, **not** a publication instant.

Evidence is a separate table with `year`, `code`, `published_at`, `availability_evidence`, and
`source_version`; it must identify the exact prepared source version and have unique municipality/
year keys. Missing evidence remains unknown; dates are never invented as `year+1`. Pass only
municipalities and geographical references whose prepared-source compatibility has been verified.
Unknown identifiers or special geographic aggregate codes must be checked by source preparation;
matching string identifiers cannot establish membership on its own.

The local sidecar identifies the nationality source cube `px-x-0102010000_101` and a 2026 update,
but lacks original historical publication/version evidence and an independently validated territorial
reference. It therefore cannot establish that this version was available in past brochure forecasts.
The adapter can expose its unknown-release coverage while the synthetic block runs populated
comparisons. Real strict forecast scores remain conditional on these missing prerequisites.

### Fitting, selection, and reservation

Historical model inputs are rebuilt at each row's own forecast: only earlier voting dates whose
results had been published with evidence are eligible. Missing comparable municipal history uses
the **admissible earlier training-only** global mean, including under rolling policy. At the first
training date, where no earlier training observation exists, the regressor's feature uses an explicit
50% cold-start prior, recorded separately in its manifest. This prior does not replace the baseline's
abstention when an evaluation forecast has no admissible training labels.

Ridge fitting uses only fit-pool labels published by the first forecast instant in that window.
Late/unknown labels cannot enter fitting. Each window fits a new estimator and preprocessing once;
the estimator, imputation, scaling and encoding stay fixed for all predictions in that window.
Numeric median imputation and scaling, categorical imputation and one-hot encoding are fit on those
training rows only. All input columns have explicit missingness indicators, including missingness
first encountered in held-out rows. Unknown held-out categories are handled without fitting an
encoder on them. Rolling history features may update after earlier outcomes are published, without
refitting the estimator. The manifest records each window's boundaries, training and validation row
keys, fitting cutoff and refit schedule.

`ridge_alphas` declares positive candidate regularization strengths (default 0.1, 1, 10, 100); the
configuration and per-model manifest record the exact grid used. Each model
fits candidates in every expanding window and selects the lowest equal-row MAE aggregated across
out-of-window validation predictions, breaking ties toward the smaller alpha. All validation objects
and municipalities on a date stay held out together. The selected validation score is a **selection
score**, not an independent post-selection performance estimate. Prediction artifacts retain raw
estimator outputs in `raw_prediction`, clipped reported shares in `prediction`, and a `clipped` flag.
Shared metrics report clipping frequency and raw prediction range alongside equal-row and
electorate-weighted MAE. Manifests record per-window candidate fits, boundaries, row keys, cutoffs,
training row counts, feature allowlists, preprocessing policy, training-design content hashes and
scikit-learn version.

### Histogram gradient boosting comparator (#44)

When prepared nontext feature blocks are supplied, the same evaluation seam adds
`hist_gradient_boosting_history`, one `hist_gradient_boosting_<block_id>` model per block, and
`hist_gradient_boosting_combined` when multiple blocks are available. Each model uses the same
history and allowlisted feature columns as its paired Ridge reference. Predictions are restricted
to the same baseline-eligible evaluation keys; raw values, clipped shares, object/date errors,
equal-row MAE, and electorate-weighted MAE use the common reporting path.

The starting validation grid contains all combinations of `max_leaf_nodes` 7/15,
`min_samples_leaf` 50/200, `learning_rate` 0.05/0.1, and `max_iter` 100. It is declared by
`EvaluationConfig.hist_gradient_boosting_candidates` and can be reduced or adjusted for verified
coverage; adjustments remain visible in the run configuration and model manifest. Settings are
selected by aggregate equal-row validation MAE across chronological windows, with deterministic
tuple ordering for ties. Automatic internal early stopping is disabled. `seed` is passed as the
estimator random state and recorded.

Boosting uses a dense allowlist-driven preparation: numeric columns receive training-only median
imputation; categorical columns receive training-only missing-value imputation and dense one-hot
encoding; all allowlisted columns receive missingness indicators. No text representation is passed
to this model. The manifest records the selected settings, candidate scores, per-window training
and evaluation keys, fitting cutoff, preprocessing, seed, scikit-learn version, and training-design
hash. A nonlinear model is a predictive comparator only; it does not support causal or individual
voter claims. Synthetic fixtures check deterministic output and pairing, not model superiority.

`selected_ridge_alphas={'ridge_history': 1.0, 'ridge_statpop_nationality': 1.0}` freezes strengths;
these runs do not use held-out targets for fitting or selection. Final-test mode requires this explicit
mapping for every reference, in addition to `choices_frozen=True`. It never selects an alpha from
test errors or emits validation-selection scores derived from test targets. References fit the declared training period by default. Setting `refit_train_validation=True` before
validation/freezing explicitly declares a final training-plus-validation refit; see
[the controlled final protocol](final_evaluation.md).

### CLI source-block manifests

`--blocks blocks.json` accepts a JSON list of descriptors. Each supplies the FeatureBlock fields
above except `records`, replaced by `records_path` pointing to a prepared CSV relative to the JSON
file. The evaluator preserves municipal/object identifier strings. Example descriptor:

```json
[{
  "block_id": "statpop_nationality", "scope": "municipality",
  "records_path": "statpop_prepared_with_evidence.csv",
  "numeric_features": ["population", "foreign_share"], "categorical_features": [],
  "definitions": {"population": "Permanent resident population, persons", "foreign_share": "Foreign / total permanent residents, share"},
  "source_url": "https://www.pxweb.bfs.admin.ch/", "source_version": "sha256:<exact-source-hash>",
  "geography_mode": "historically_existing"
}]
```

Use `python3 -m scripts.evaluate_votes --input votes_prepared.csv --config experiment.json
--blocks blocks.json --output /tmp/run` (on one command line). All joined features, selection
manifests, matched publication evidence, coverage and paired prediction keys are reproducible
artifacts. The source CSV must already include the record contract; the CLI does not guess how to
join an unevidenced raw population file.

### Paired brochure text experiment

Supply `--text-records reviewed-records.json` (a JSON list using the reviewed
record contract in `scripts/forecast_text_export.py`), or pass `text_records`
to `evaluate`. The evaluator reruns the version-bound export gate; unknown
availability, stale source decisions, ambiguous correspondence and invalid
extractions cannot enter the experiment. It additionally requires the document's
voting date and exact brochure forecast instant to match the prepared object.
The text branch explicitly selects `summary_official` from each validated
object record; generic text and full-text fields are never fallback sources.
Object mapping, semantic validity, source hash and exact-version availability
remain enforced by the export gate. French is the selected language. Non-French
records are excluded and reported; when no French summary or no eligible summary
exists, the text branch records a prerequisite skip while nontext results remain.

`text_experiment` reports a paired regularized nontext reference and additive
TF-IDF model on identical municipal row keys, using history and every supplied
admissible feature block. Both fit the same eligible training rows. At each
shared chronological window, vocabulary and IDF are fitted on one summary per
distinct eligible training object, then joined to municipal observations.
Vectorizer, preprocessing and estimator stay fixed within the window. Held-out
objects cannot influence vocabulary, IDF, imputation, scaling or categorical
encoding. Repeated municipal instances do not change the brochure text
representation. Model fitting remains at the municipal observation level. Text
contributes a shared object shift across municipalities before predictions are
clipped to [0, 1].

Initial word TF-IDF settings are unigrams and bigrams, L2 normalization,
`min_df=2` objects, `max_df=0.95`, and at most 2,000 features. Each window
records its vocabulary, IDF, training object keys, exact source hashes, and
effective settings. If a small training corpus makes those minimum/maximum
frequency cutoffs incompatible, the recorded fold adjustment raises `max_df`
to 1.0; with fewer than two training objects, it also lowers `min_df` to 1.
Empty vocabularies are reported per window. Held-out vocabulary never enters
fitting.

Each model selects its own ridge alpha on chronological validation. Freeze the
returned `models.*.selected_alpha` values as `selected_ridge_alphas` keys
`paired_nontext` and `paired_text` for final-test runs. Final-test mode requires
these choices and never selects using test targets. Empty eligible training or
evaluation corpora, including texts without vocabulary tokens, explicitly skip
the text experiment while broader nontext evaluation continues.

The separate text report includes rows, distinct objects and dates; paired MAE;
errors by object/date; excluded document reasons; forecast mismatches; and rows
and objects lost relative to broader nontext predictions. Broader nontext metrics
remain in the main report. `text_predictions.csv` contains paired predictions;
`summary.json` records vocabulary, IDF, per-training-object vectors, settings,
source hashes and frozen choices for auditing and repeat-instance checks.
