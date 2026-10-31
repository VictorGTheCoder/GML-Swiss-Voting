# Reproduce the November 3 municipal model demonstration

This is **exploratory retrospective validation**, separate from strict V1, which
still has zero eligible rows. No release evidence is invented and the strict
`evaluate_votes` contract is unchanged. Issues [#61](https://github.com/VictorGTheCoder/GML-Swiss-Voting/issues/61)
and [#51](https://github.com/VictorGTheCoder/GML-Swiss-Voting/issues/51) define the model
and academic deliverable. This bounded demonstration does not complete all of #51.

## Install and run

From a clean checkout of this PR, use Python 3.12 (the executed environment uses
3.12; exact runtime versions are recorded in the manifest):

```bash
python3.12 -m venv .venv-demo
.venv-demo/bin/python -m pip install -r requirements-demo.txt
```

If the system Python lacks `ensurepip`/venv support, the equivalent tested setup is
`uv venv --python python3.12 .venv-demo` followed by
`uv pip install --python .venv-demo/bin/python -r requirements-demo.txt`.

On Windows, use `.venv-demo\Scripts\python.exe` instead. The one training command,
from the repository root, is:

```bash
.venv-demo/bin/python -m scripts.modeling.retrospective_demo
```

No downloads or source reconstruction are required: the prepared inputs are
versioned. `--output PATH` changes the artifact directory. Thread pools are limited
to one during fitting and prediction. The command verifies all five source hashes
and the exact notebook dataset hash, validates the feature allowlists, keys,
retrospective geography and source selection thresholds, recomputes frozen history
using the original source cleaning rules, then fits preprocessing on training only.
A changed input fails closed and requires a newly audited experiment, rather than
silently reporting the old scores. Reserved-test row groups are filtered before
loading targets; file hashes cover the immutable source bytes, including the
reserved period, without inspecting its outcomes.

The executed [original notebook](../../notebooks/modeling/01_hist_gradient_boosting.ipynb)
is recovered from commit `6741747853304ed2d2e16f66e13b60cb52020615` on
`61-test-modèle-histgradientboostingregressor`. Its dataset SHA-256 matches main.
Its retained outputs are historical evidence; use the command above for the complete
deliverable. The runner extracts its model/preprocessing and historical split policy,
reuses `clean_outcomes` and shared scoring, and adds fixed-alpha Ridge through the
existing regularized-model preprocessing. It deliberately does not feed the
unevidenced exploratory table into the strict evaluator. The strict evaluator's
one-hot boosting model has a different representation and is not the recovered
native-categorical notebook experiment.

## Artifacts and exact results

Outputs under `reports/generated/retrospective_demo/`:

- `boosting.joblib`: fitted preprocessing and estimator, feature list and provenance.
- `validation_predictions.parquet`: paired validation keys, targets, model names,
  raw and clipped predictions; no reserved-test predictions.
- `validation_metrics.csv`, `validation_by_object.csv`, `validation_by_date.csv`.
- `partitions.csv`, `run_manifest.json`: evaluated periods, inputs and runner hashes,
  versions, assumptions, cleaning exclusions, feature settings and artifact hash.
- Three presentation figures in PNG and SVG, plus `presentation.md`.

The runner reloads the persisted pipeline and requires bit-identical validation
predictions before completing. No fitting occurs during artifact reload. To use it:

```python
import joblib
from scripts.modeling.retrospective_demo import model_input
bundle = joblib.load('reports/generated/retrospective_demo/boosting.joblib')
# frame must contain the documented features with history already frozen at end 2020.
raw_shares = bundle['pipeline'].predict(model_input(frame))
shares = raw_shares.clip(0, 1)
```

Joblib is a Python artifact tied to the pinned environment; load only trusted
artifacts. The fitted preprocessing is saved, while deterministic history assembly
remains the documented data preparation step.

The versioned [presentation and measured results](../../reports/datasets/retrospective_demo/presentation.md)
include limitations and the figures. Generated binaries stay outside Git;
regenerating the artifact is part of the single command. Comparison uses the same
50,520 validation keys (24 objects, seven dates, 2,105 municipalities) for every model.
Train: 174,571 rows, 83 objects, 30 dates. Validation shares are never used in
preprocessing, history, fitting or hyperparameter search. Test 2023–2025 remains
reserved. No operational forecasting claim follows from retrospective features.

Ridge's alpha is fixed at 1, without a search. The history-only and combined Ridge
scores satisfy a useful nontext comparison, but source-specific ablations, strict
brochure-publication-time evaluation and independently recorded teammate reproduction
remain future work. A successful second run by this agent is not a teammate's
independent replication.

## Verification

```bash
python -m pytest tests -q
python -m ruff check scripts tests
```

The added complete-run synthetic test checks identical comparison keys, train-only
encoding, unknown categories, training-only removal of empty features, persisted
pipeline reload, held-out-target isolation and absence of final-test exports.
Existing source preparation and strict evaluator tests continue to establish their
own contracts. Real-data results and input compatibility are verified by the demo
command, rather than inferred from synthetic tests.

The two plotted examples are the Film Act amendment (vote `6550`, MAE 4.591249 pp)
and Frontex participation (vote `6570`, MAE 26.848529 pp), both on 2022-05-15.
Titles come from the versioned Swissvotes short English title field and serve
only as presentation labels, never model features.

## Feature definitions and compatibility

| Features | Definition and unit |
| --- | --- |
| `history_mean_yes`, `history_n_objects` | Equal-object mean yes share [0,1] and count of eligible earlier municipal objects; pre-2012 included, frozen after 2020. |
| `statpop_pop_total` | Permanent resident population, persons, sexes combined. |
| `statpop_share_foreign` | Foreign permanent residents / total permanent residents, fraction [0,1]. |
| `statpop_share_0_19`, `20_39`, `40_64`, `65_plus`, `80_plus` | Each named age group's population / total permanent residents, fraction [0,1]; 80+ overlaps 65+. All names have the `statpop_share_` prefix. |
| `statpop_mean_age` | Count-weighted age in years; the 100+ bin is represented as age 100. |
| Nine `party_share_*` fields | Previous National Council election party vote strength as fractions [0,1]; PLR, PDC, PS, UDC, PEV, Greens, PVL, PBD and Centre remain distinct. Missing parties remain missing, not zero. |
| `urban_rural`, `language_region` | Nominal OFS typology and language-region codes on the 2026 municipal snapshot. |
| `object_legal_form`, `object_domain_1/2/3` | Nominal Swissvotes legal-form and three broad domain codes; numeric-looking codes are categories. |
| `history_missing`, `statpop_missing`, `elections_missing` | Boolean absence flags, represented as 0/1; history flag recomputed after freezing. |

Main's prepared OFS, STATPOP, election and typology tables use the same four-character
municipality IDs on the retrospective 2026-01-01 reference. Existing preparation
aggregates counts before calculating merged municipal shares. Swissvotes joins use
exact `vote_key` plus independently checked date/question type. All source bytes and
the derived snapshot match the notebook's manifest; no new joins or geographic
allocation are introduced by the demonstration. These checks establish structural
compatibility under the retrospective assumptions, not historical availability.
