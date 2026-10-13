# Controlled municipal prediction evaluation

The principal reproducible run uses the complete evaluation boundary from issue #33. Prepared
sources, chronological date partitions, source blocks, brochure text representation and forecast
instants remain explicit inputs. Ordinary validation does not produce final-test scores.

## Reproduce validation, freeze, and final evaluation

From the repository root in its Python environment:

```bash
python3 -m scripts.evaluate_votes --synthetic --synthetic-features --synthetic-text --output /tmp/swiss-voting/validation --freeze-output /tmp/swiss-voting/frozen.json
python3 -m scripts.evaluate_votes --synthetic --synthetic-features --synthetic-text --final-test --frozen-experiment /tmp/swiss-voting/frozen.json --output /tmp/swiss-voting/final
python3 -m pytest -q tests/test_final_evaluation.py
```

Synthetic brochure evidence, source versions and geography are illustrative fixtures. These commands
verify the complete contract; they do not establish Swiss forecast accuracy. The default synthetic
example contains one held-out date per partition, so intervals are explicitly unavailable owing to
insufficient dates. Fixtures with several dates verify the complete-date uncertainty calculation.

Omit `--synthetic-text` in both commands to reproduce a nontext-only experiment. The same pipeline
handles a reviewed text corpus with no eligible objects: it records the skipped text branch and
continues nontext evaluation. A branch skipped during frozen validation stays skipped in the final
run, even when a declared refit could now find more training texts; final testing cannot silently
introduce a model family without prior validation choices.

For real prepared inputs, validation uses `--input votes.csv --config experiment.json --blocks
blocks.json --text-records reviewed_text.json` and optional `--crosswalk crosswalk.csv`. Keep each
command on one line. Add `--freeze-output frozen.json`, then run the same sources with
`--final-test --frozen-experiment frozen.json`. Final mode can recover its config from the artifact
without `--config`; supplying a different config is rejected by the freeze check.

## What is frozen before final testing

`freeze_experiment(validation_result)` creates an integrity-checked JSON artifact only from a
validation run. It records date partitions, predictor allowlists, block definitions and hashes,
selected Ridge strengths for each nontext and paired-text variant, preprocessing policies,
TF-IDF settings, geographical mode/crosswalk provenance, source versions, forecast cutoffs,
prepared publication metadata, rolling-history policy, fit-period policy, evaluation weight origin,
seed and uncertainty settings. It also pins implementation file hashes and environment versions.
Outcome values are excluded from the prepared metadata signature; fitting and model selection still
never read test targets. Feature source data, text records and territorial/publication evidence are
pinned separately. Changing those inputs requires a fresh validation/freeze cycle.

The CLI requires both `--final-test` and `--frozen-experiment`. It verifies the artifact integrity and
source/configuration compatibility **before** final fitting or scoring. Strengths come from the
validation artifact; no test error is used to choose them. Direct Python callers may still supply an
explicit final configuration with `choices_frozen=True` and the selected strengths, for compatibility
with the existing evaluation API. Supplying `frozen_experiment=artifact` adds the full integrity and
source-policy guards and is the reproducible final workflow.

## Fit periods and rolling history

`refit_train_validation=False` retains training-only fitting. Set `refit_train_validation=True` in the
configuration **before validation and freezing** to declare a final training-plus-validation refit.
Validation fitting remains training-only. In the final run, only declared training/validation labels
published by the earliest scored forecast can enter fitting. Test labels never fit imputers, scalers,
encoders, coefficients or vocabulary. Text refit uses one document per eligible training/validation
object before repeating vectors for municipal observations. Candidate strengths remain frozen.

Frozen history admits the declared fit-period history and never earlier test targets. Rolling history
may additionally use results of earlier held-out objects, including earlier test dates, only after
their documented publication and before the later forecast instant. This policy is shared by the
municipal baseline, nontext reference model and paired additive-text model. Same-date objects never
update one another. Fallback for missing comparable municipal history always uses the original
admissible training-only global mean; it does not consume validation or test labels. The explicit
50% feature prior at the first training date remains distinct from that learned fallback. These
histories update predictors, not the fitted regression or preprocessing between test dates.

## Scores, weights, uncertainty and artifacts

Top-level metrics and errors by object/date cover the wider nontext population. Nested
`text_experiment` metrics and errors cover identical rows for `paired_nontext` and `paired_text`.
Text coverage reports losses relative to the wider nontext population. `paired_uncertainty` compares
model pairs on their shared municipality/object keys and states paired row, object and date counts.
Cross-population comparisons therefore disclose their restricted population.

MAE is in percentage points, with equal municipal-observation weight. Complementary
electorate-weighted MAE uses prepared `evaluation_weight` only for evaluation; positive finite
weights are retained and weight coverage is reported. Set `evaluation_weight_origin` to the exact
retrospective source/version/definition, for example the electorate count of the evaluated object
in a named voting-result version. Unspecified provenance is labelled as such; missing weights yield
no weighted score. Evaluation weights do not automatically qualify as forecast-time predictors.

Paired uncertainty samples **complete held-out voting dates with replacement**, carrying every
paired observation on each selected date. It recomputes equal-row and complementary weighted MAE
differences for each replicate; municipal rows are never resampled independently. `seed` and
`bootstrap_replicates` (default 1000) make results deterministic. Differences are right-model MAE
minus left-model MAE; negative favors the right model. Empirical 2.5/97.5 percentiles are reported
only when at least two paired dates exist. Three sampled-date/row-count audits make the grouping
reviewable. Few dates can produce unstable intervals; this procedure does not model possible
serial dependence. Validation selection scores and their intervals are subject to model-selection
optimism and do not substitute for the reserved final evaluation.

Each output directory includes `summary.json`, `partitions.csv`, `eligible_rows.csv`,
`predictions.csv`, `model_summary.csv`, `joined_features.csv`, `join_report.csv`, `by_object.csv`, `by_date.csv` and,
when requested, `text_predictions.csv`. The summary contains source/configuration provenance,
coverage/exclusions, independent source ablations, selected models, paired uncertainty and text
eligibility/representation reports. The final manifest records the frozen artifact hash. Artifacts
are deterministic for identical prepared inputs/configuration and remain outside tracked source.

## Real source prerequisites and interpretation

The cleaned municipal outcome table alone has no evidenced brochure forecast instants, original
historical result publication/version availability or independently verified territorial mappings.
The prepared STATPOP nationality sidecar records a recent cube update rather than historical
releases. Official brochure text requires reviewed object matches, semantic extraction and
availability evidence bound to the exact source hash at the actual forecast instant. Unknown
metadata remains missing/excluded or a clearly recorded skipped branch; publication dates and
territorial crosswalks are never invented.

See [the prepared contract and source-block protocol](municipal_evaluation.md) and
[the forecast-time text gates](../forecast-text-export.md). Retrospective fixed-geography results must remain
labelled retrospective. Negative or worse incremental results are valid outcomes. These comparisons
estimate municipal prediction error; they do not establish brochure causality or individual behavior.
