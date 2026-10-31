"""Reproduce #61's retrospective validation; never evaluate the reserved test.

Run from the repository root: python -m scripts.modeling.retrospective_demo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

from scripts.common.config import ROOT
from scripts.integration.build_modeling_dataset import DEMOGRAPHICS, OBJECT_FIELDS, PARTIES, TYPOLOGIES, clean_outcomes
from scripts.modeling.regularized_votes import _pipeline as ridge_pipeline
from scripts.modeling.vote_metrics import score_predictions

matplotlib.use('Agg')
import matplotlib.pyplot as plt

TRAIN_END = pd.Timestamp('2020-12-31')
VALIDATION_END = pd.Timestamp('2022-12-31')
DATASET_SHA256 = 'c8a488826093a53f307af0b4a04627fa6d78118a8ac4b25ca8c8e097fdf8e043'
NOTEBOOK_COMMIT = '6741747853304ed2d2e16f66e13b60cb52020615'
NUMERIC = ['history_mean_yes', 'history_n_objects'] + [f'statpop_{c}' for c in DEMOGRAPHICS] + [
    f'party_share_{c}' for c in PARTIES.values()]
CATEGORICAL = TYPOLOGIES + list(OBJECT_FIELDS.values())
INDICATORS = ['history_missing', 'statpop_missing', 'elections_missing']


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen_history(targets, outcomes):
    """Recovered notebook policy: strictly earlier dates, capped at end of training."""
    pool = outcomes.loc[outcomes.vote_date.le(TRAIN_END)]
    result = pd.DataFrame(index=targets.index, columns=[
        'history_mean_yes', 'history_n_objects', 'history_last_vote_date'])
    for date, group in targets.groupby('vote_date', sort=True):
        past = pool.loc[pool.vote_date.lt(date)]
        stats = past.groupby('municipality_id').agg(
            history_mean_yes=('yes_share', 'mean'), history_n_objects=('yes_share', 'count'),
            history_last_vote_date=('vote_date', 'max'))
        for column in result:
            result.loc[group.index, column] = group.municipality_id.map(stats[column]).to_numpy()
    result['history_mean_yes'] = pd.to_numeric(result.history_mean_yes)
    result['history_n_objects'] = pd.to_numeric(result.history_n_objects).fillna(0).astype('int64')
    result['history_last_vote_date'] = pd.to_datetime(result.history_last_vote_date)
    result['history_missing'] = result.history_mean_yes.isna()
    return result


def model_input(frame):
    result = frame[NUMERIC + CATEGORICAL + INDICATORS].copy()
    for column in NUMERIC + INDICATORS:
        result[column] = result[column].astype(float)
    for column in CATEGORICAL:
        result[column] = result[column].astype(object).where(result[column].notna(), np.nan)
    return result


def notebook_pipeline(train):
    """Exact native-categorical preprocessing/settings from the executed #61 notebook."""
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder

    empty = train.columns[train.isna().all()].tolist()
    numeric = [c for c in NUMERIC + INDICATORS if c not in empty]
    categorical = [c for c in CATEGORICAL if c not in empty]
    if train[categorical].nunique().gt(255).any():
        raise ValueError('Native categorical cardinality exceeds max_bins=255')
    prepare = ColumnTransformer([
        ('numeric', 'passthrough', numeric),
        ('categorical', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=np.nan,
                                      encoded_missing_value=np.nan, dtype=float), categorical),
    ], sparse_threshold=0)
    settings = {'loss': 'squared_error', 'learning_rate': 0.1, 'max_iter': 100, 'max_leaf_nodes': 31,
                    'min_samples_leaf': 20, 'l2_regularization': 0.0, 'early_stopping': False, 'random_state': 42}
    model = Pipeline([('prepare', prepare), ('regressor', HistGradientBoostingRegressor(
        **settings, categorical_features=[False] * len(numeric) + [True] * len(categorical)))])
    return model, empty, settings


def load_inputs(root):
    directory = root / 'data/processed/modeling'
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['mode'] != 'exploratory_retrospective' or manifest['strict_forecast_ready'] is not False:
        raise ValueError('Expected the separately identified retrospective dataset')
    for field, expected in [('numeric_features', NUMERIC), ('categorical_features', CATEGORICAL),
                            ('missing_indicators', INDICATORS), ('target', 'yes_share')]:
        if manifest[field] != expected:
            raise ValueError(f'Feature contract changed: {field}')
    for source in manifest['sources'].values():
        if sha256(root / source['path']) != source['sha256']:
            raise ValueError(f'Source changed; rebuild and audit the modeling dataset: {source["path"]}')
    path = directory / 'municipal_structured.parquet'
    if sha256(path) != DATASET_SHA256:
        raise ValueError('Dataset differs from executed #61 snapshot; audit before changing the frozen experiment')
    # Arrow predicate filtering: no reserved-test target values enter this experiment.
    data = pd.read_parquet(path, filters=[('vote_date', '<=', VALIDATION_END)])
    if (data.duplicated(['municipality_id', 'vote_id']).any() or
            data[['municipality_id', 'vote_id', 'vote_date']].isna().any().any() or
            not data.groupby('vote_id').vote_date.nunique().eq(1).all() or
            not data.yes_share.between(0, 1).all() or not np.isfinite(data.yes_share).all()):
        raise ValueError('Invalid keys, dates or target')
    if not data.geography_id.eq('retrospective_fixed_2026-01-01').all() or data.strict_forecast_ready.any():
        raise ValueError('Unexpected geography or forecasting status')
    for field in ['statpop_selection_from', 'election_selection_from']:
        if (data[field].notna() & data[field].gt(data.vote_date - pd.Timedelta(days=1))).any():
            raise ValueError(f'Future source selected: {field}')
    history_path = root / manifest['sources']['ofs']['path']
    source = pd.read_parquet(history_path, filters=[('vote_date', '<=', TRAIN_END)])
    outcomes, exclusions = clean_outcomes(source)
    history = frozen_history(data, outcomes)
    train = data.vote_date.le(TRAIN_END)
    np.testing.assert_allclose(history.loc[train, 'history_mean_yes'].to_numpy(dtype=float),
                               data.loc[train, 'history_mean_yes'].to_numpy(dtype=float), equal_nan=True)
    if (history.history_last_vote_date.notna() & (
            history.history_last_vote_date.ge(data.vote_date) | history.history_last_vote_date.gt(TRAIN_END))).any():
        raise ValueError('History contains a same-date or held-out outcome')
    data[history.columns] = history
    data['partition'] = np.where(train, 'train', 'validation')
    if data.groupby('vote_date').partition.nunique().gt(1).any() or set(data.partition) != {'train', 'validation'}:
        raise ValueError('Invalid date partitions')
    return data, manifest, exclusions


def report_metrics(predictions):
    scores, objects, dates = [], [], []
    for name, group in predictions.groupby('model', sort=False):
        errors = group.assign(absolute_error_pp=(group.prediction - group.target_share).abs() * 100)
        by_object = errors.groupby(['vote_id', 'vote_date'], as_index=False).absolute_error_pp.mean()
        by_date = errors.groupby('vote_date', as_index=False).absolute_error_pp.mean()
        scores.append({'model': name, **score_predictions(group),
                       'mean_object_mae_pp': float(by_object.absolute_error_pp.mean()),
                       'mean_date_mae_pp': float(by_date.absolute_error_pp.mean())})
        objects.append(by_object.assign(model=name))
        dates.append(by_date.assign(model=name))
    return pd.DataFrame(scores), pd.concat(objects), pd.concat(dates)


def figures(predictions, scores, objects, output):
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.hashsalt': 'swiss-voting-demo'})
    def save(fig, name):
        fig.savefig(output / f'{name}.png', dpi=200, bbox_inches='tight')
        svg = output / f'{name}.svg'
        fig.savefig(svg, bbox_inches='tight', metadata={'Date': None})
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.barh(scores.model, scores.mae_pp, color='#2563a6')
    for i, value in enumerate(scores.mae_pp):
        ax.text(value + .1, i, f'{value:.3f}', va='center')
    ax.set(xlim=(0, scores.mae_pp.max() + 2), xlabel='Municipality–object MAE (percentage points)',
           title='Retrospective validation · 2021–2022')
    save(fig, 'validation_mae')
    boosting = predictions.loc[predictions.model.eq('hist_gradient_boosting')].copy()
    boosting['error_pp'] = (boosting.prediction - boosting.target_share) * 100
    ranked = objects.loc[objects.model.eq('hist_gradient_boosting')].sort_values(['absolute_error_pp', 'vote_id'])
    labels = [f'{row.vote_date:%Y-%m-%d} · {row.vote_id}' for row in ranked.itertuples()]
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.boxplot([boosting.loc[boosting.vote_id.eq(v), 'error_pp'] for v in ranked.vote_id],
               orientation='horizontal', tick_labels=labels, showfliers=False)
    ax.axvline(0, color='#2563a6', linewidth=1)
    ax.set(xlabel='Predicted − observed yes share (percentage points); outliers hidden',
           title='Boosting errors by voting object · ordered by object MAE')
    save(fig, 'errors_by_object')
    examples = ranked.iloc[[0, -1]]
    fig, axes = plt.subplots(1, 2, figsize=(10, 5), sharex=True, sharey=True)
    for ax, row, label in zip(axes, examples.itertuples(), ['Lowest object MAE', 'Highest object MAE']):
        group = boosting.loc[boosting.vote_id.eq(row.vote_id)]
        ax.scatter(group.target_share * 100, group.prediction * 100, s=7, alpha=.25, color='#2563a6')
        ax.plot([0, 100], [0, 100], color='#666666', linestyle='--')
        ax.set(xlim=(0, 100), ylim=(0, 100), xlabel='Observed yes share (%)',
               title=f'{label}\n{row.vote_date:%Y-%m-%d} · {row.vote_id}\nMAE {row.absolute_error_pp:.3f} pp')
        ax.set_aspect('equal')
    axes[0].set_ylabel('Predicted yes share (%)')
    fig.suptitle('Retrospective validation · examples selected by boosting object MAE')
    fig.tight_layout()
    save(fig, 'prediction_examples')
    return examples


def run(root, output, include_ridge=True):
    output.mkdir(parents=True, exist_ok=True)
    data, source_manifest, exclusions = load_inputs(root)
    train, validation = (data.loc[data.partition.eq(p)] for p in ['train', 'validation'])
    x_train, x_validation = model_input(train), model_input(validation)
    model, empty, settings = notebook_pipeline(x_train)
    constant = float(train.yes_share.mean())
    raw_predictions = {'constant': np.full(len(validation), constant),
                       'municipal_history': validation.history_mean_yes.fillna(constant).to_numpy(dtype=float)}
    with threadpool_limits(limits=1):
        model.fit(x_train, train.yes_share.astype(float))
        raw_predictions['hist_gradient_boosting'] = model.predict(x_validation)
        if include_ridge:
            for name, numeric, categorical in [
                ('ridge_history', ['history_mean_yes', 'history_missing'], []),
                ('ridge_combined', NUMERIC + INDICATORS, CATEGORICAL),
            ]:
                ridge = ridge_pipeline(numeric, categorical, 1.0)
                ridge.fit(x_train, train.yes_share.astype(float))
                raw_predictions[name] = ridge.predict(x_validation)
    frames = []
    for name, raw in raw_predictions.items():
        if not np.isfinite(raw).all():
            raise ValueError(f'Nonfinite predictions: {name}')
        frame = validation[['municipality_id', 'vote_id', 'vote_date', 'yes_share']].rename(
            columns={'yes_share': 'target_share'}).copy()
        frame['model'], frame['raw_prediction'] = name, raw
        frame['prediction'] = np.clip(raw, 0, 1)
        frame['clipped'] = raw != frame.prediction
        frames.append(frame)
    predictions = pd.concat(frames, ignore_index=True)
    scores, objects, dates = report_metrics(predictions)
    examples = figures(predictions, scores, objects, output)
    partitions = data.groupby('partition').agg(rows=('vote_id', 'size'), objects=('vote_id', 'nunique'),
        dates=('vote_date', 'nunique'), municipalities=('municipality_id', 'nunique'),
        first_date=('vote_date', 'min'), last_date=('vote_date', 'max'))
    manifest = {
        'mode': 'exploratory_retrospective', 'strict_forecast_ready': False, 'test_evaluated': False,
        'notebook_commit': NOTEBOOK_COMMIT, 'seed': 42, 'thread_limit': 1, 'settings': settings,
        'train_end': str(TRAIN_END.date()), 'validation_end': str(VALIDATION_END.date()),
        'reserved_test': '2023–2025; no targets loaded, predictions or scores generated',
        'history_policy': 'strictly earlier dates, including pre-2012; frozen at 2020-12-31',
        'refit_train_validation': False, 'hyperparameter_search': False, 'ridge_alpha': 1.0 if include_ridge else None,
        'features': NUMERIC + CATEGORICAL + INDICATORS, 'excluded_all_missing_training_features': empty,
        'preprocessing': 'training-only ordinal encoding; native missing values and categorical splits',
        'constant_prediction': constant, 'history_validation_fallbacks': int(validation.history_mean_yes.isna().sum()),
        'sources': source_manifest['sources'], 'assumptions': source_manifest['blocks'],
        'dataset_sha256': sha256(root / 'data/processed/modeling/municipal_structured.parquet'),
        'dataset_manifest_sha256': sha256(root / 'data/processed/modeling/manifest.json'),
        'source_exclusions_before_training_cutoff': exclusions,
        'dataset_exclusions_sequential': source_manifest['exclusions_sequential'],
        'partition_dates': {p: sorted(g.vote_date.dt.strftime('%Y-%m-%d').unique().tolist())
                            for p, g in data.groupby('partition')},
        'versions': {'python': platform.python_version(), 'sklearn': sklearn.__version__,
                     'pandas': pd.__version__, 'numpy': np.__version__, 'joblib': joblib.__version__},
        'example_selection': 'minimum and maximum boosting object MAE; ties ordered by vote_id',
        'example_vote_ids': examples.vote_id.tolist(),
    }
    joblib.dump({'pipeline': model, 'features': NUMERIC + CATEGORICAL + INDICATORS, 'manifest': manifest},
                output / 'boosting.joblib')
    with threadpool_limits(limits=1):
        loaded = joblib.load(output / 'boosting.joblib')
        np.testing.assert_array_equal(loaded['pipeline'].predict(x_validation), raw_predictions['hist_gradient_boosting'])
    manifest['artifact_reload_predictions_identical'] = True
    predictions.to_parquet(output / 'validation_predictions.parquet', index=False)
    scores.to_csv(output / 'validation_metrics.csv', index=False)
    objects.to_csv(output / 'validation_by_object.csv', index=False)
    dates.to_csv(output / 'validation_by_date.csv', index=False)
    partitions.to_csv(output / 'partitions.csv')
    manifest['runner_sha256'] = sha256(Path(__file__))
    manifest['artifact_sha256'] = sha256(output / 'boosting.joblib')
    (output / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    summary = f"""# Municipal yes-share prediction · 3 November 2026 demonstration

**Retrospective exploratory validation; operational forecasting is not demonstrated.**

## Research objective

Predict municipal yes-vote share (`yes / (yes + no)`) for a federal voting object
from earlier voting history, municipal characteristics and object categories.
The broader research question asks whether brochure text adds value; this experiment
establishes a nontext reference and does not answer the text question.

## Dataset and protocol

One observation is municipality × object. Reuse the frozen #61 structured snapshot
on retrospective 2026 geography. Train on 2012–2020 ({len(train):,} rows,
{train.vote_id.nunique()} objects, {train.vote_date.nunique()} dates); validate on
2021–2022 ({len(validation):,} rows, {validation.vote_id.nunique()} objects,
{validation.vote_date.nunique()} dates). Reserved test: 2023–2025, untouched.
History includes pre-2012 outcomes, excludes every same-day object, and freezes at
2020-12-31 for validation. No train-plus-validation refit or parameter search.

Inputs: two history features, eight STATPOP features, nine party shares, six
categorical typology/object fields and three missingness flags. Boosting excludes
`party_share_centre` using training missingness only (27 effective predictors).
STATPOP uses the assumed September Y+1 selection rule; elections use a strictly
previous election year; current typologies and Swissvotes categories are retrospective.
Feature roles and temporal rules: `data/processed/modeling/feature_dictionary.csv`;
definitions and units: `docs/project/retrospective_demo.md`.
Source hashes, assumptions, exclusions and exact split dates are in `run_manifest.json`.

## Models and validation results

Constant = training-row mean. Municipal history = frozen municipal mean, with
{int(validation.history_mean_yes.isna().sum())} missing histories falling back to the constant.
Boosting uses native categorical splits and missing values, training-only ordinal
encoding, 100 iterations, learning rate 0.1, 31 leaves, minimum leaf size 20,
seed 42, no internal early stopping. Ridge reuses existing preprocessing
(median imputation, scaling, one-hot encoding and missingness), fixed alpha 1.
All models use identical validation keys and predictions clipped to [0, 1].

{scores[['model', 'mae_pp', 'mean_object_mae_pp', 'mean_date_mae_pp']].to_markdown(index=False, floatfmt='.6f')}

All metrics are MAE in percentage points. `mae_pp` weights every municipality–object
row equally, not population or electorate. `mean_object_mae_pp` weights each object's
municipal MAE equally. They coincide here because every validation object has 2,105
municipalities. `mean_date_mae_pp` weights each of the seven dates equally.
These are reused validation comparison scores, not independent final estimates.

![Validation MAE](validation_mae.png)
![Signed municipal errors by object](errors_by_object.png)
![Prediction examples](prediction_examples.png)

Examples are the lowest and highest boosting object MAE, with ties ordered by
vote ID: {', '.join(map(str, examples.vote_id))}. This rule deliberately displays a
success and a failure; it is not a random sample. The error boxes show median,
quartiles and 1.5-IQR whiskers; extreme points are hidden only in the figure.
All predictions remain in the exported Parquet. PNG and SVG versions are generated.

## Limitations and next steps

Strict V1 still has zero historically eligible rows: publication evidence is
missing. This run neither changes nor passes its eligibility gate. Historical
release versions of results/features, election selection timing, static 2026
geography and current object classifications prevent an operational forecasting
claim. No same-date or held-out outcomes enter features or fitting, but historical
availability leakage cannot be ruled out without evidence. Current municipal
blocks are structurally compatible, not verified historical vintages.

Only 24 validation objects across seven dates underpin these results; municipal
observations within an object are dependent. No uncertainty interval, causal claim,
individual-voter inference or held-out-test performance is established. The notebook
had already exposed validation results; model-family comparisons reuse that set.

Next: have a teammate independently run the pinned command and record their version
and hashes (not yet done); establish publication/version and territorial evidence;
then compare history-only and integrated features under the strict protocol.
Brochure text remains deferred until its gate passes. Keep final-test choices frozen
before any later authorized test evaluation. Tuesday's deliverable is this reproducible
nontext demonstration, not completion of the broader research program.
"""
    (output / 'presentation.md').write_text(summary, encoding='utf-8')
    print(scores[['model', 'mae_pp', 'mean_object_mae_pp', 'mean_date_mae_pp']].to_string(index=False))
    print(f'Artifacts: {output}; reserved test untouched.')
    return predictions, scores, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/generated/retrospective_demo')
    parser.add_argument('--without-ridge', action='store_true')
    args = parser.parse_args()
    run(ROOT, args.output, include_ridge=not args.without_ridge)


if __name__ == '__main__':
    main()
