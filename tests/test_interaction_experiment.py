"""Guard cold-start predictions, exact object joins and train-only interactions."""
import numpy as np
import pandas as pd
import pytest

from scripts.modeling import interaction_experiment as experiment
from scripts.modeling import retrospective_demo as demo


def frames():
    rng = np.random.default_rng(49)
    data = pd.DataFrame({c: rng.uniform(size=16) for c in demo.NUMERIC + demo.INDICATORS})
    for c in demo.CATEGORICAL:
        data[c] = np.repeat(['a', 'b', 'a', 'b', 'a', 'b', 'new', 'new'], 2)
    data['vote_id'] = np.repeat([f'v{i}' for i in range(8)], 2)
    data['vote_key'] = data.vote_id
    data['municipality_id'] = ['0001', '0002'] * 8
    data['vote_date'] = pd.to_datetime(np.repeat(
        ['2013-01-01', '2013-03-01', '2014-01-01', '2014-03-01',
         '2015-01-01', '2015-03-01', '2016-01-01', '2016-03-01'], 2))
    data['yes_share'] = rng.uniform(size=16)
    source = data[['vote_key', 'vote_date']].drop_duplicates().copy()
    for c in experiment.PARTIES.values():
        source[f'p-{c}'] = ['1', '2', '3', '4', '5', '9999', None, '2']
    joined = experiment.attach_recommendations(data, source)
    return joined.iloc[:12].copy(), joined.iloc[12:].copy(), source


def test_recommendations_preserve_semantics_and_missingness():
    train, evaluation, source = frames()
    data = pd.concat([train, evaluation])
    assert data.recommendation_plr.drop_duplicates().tolist()[:6] == ['1', '2', '3', '4', '5', '9999']
    expected = data.party_share_plr.iloc[:4].to_numpy() * [1, 1, -1, -1]
    np.testing.assert_allclose(data.cue_plr.iloc[:4], expected)
    assert data.cue_plr.iloc[4:10].eq(0).all()
    assert data.cue_plr.iloc[10:14].isna().all()
    bad = source.copy()
    bad.loc[0, 'vote_date'] = pd.Timestamp('2020-01-01')
    with pytest.raises(ValueError, match='dates disagree'):
        experiment.attach_recommendations(data.drop(columns=experiment.RECOMMENDATIONS + experiment.CUES), bad)
    with pytest.raises(ValueError, match='unique'):
        experiment.attach_recommendations(data, pd.concat([source, source.iloc[:1]]))


def test_theme_interactions_can_reverse_a_local_effect():
    train, evaluation, _ = frames()
    # Completely crossed local profile and theme, repeated enough to identify the interaction.
    x = pd.concat([train.iloc[:4]] * 20, ignore_index=True)
    x[demo.NUMERIC + demo.INDICATORS] = .5
    x[demo.CATEGORICAL] = 'constant'
    x['object_domain_1'] = ['a', 'a', 'b', 'b'] * 20
    x['party_share_udc'] = [0., 1., 0., 1.] * 20
    target = np.array([.2, .8, .8, .2] * 20)
    a, b = experiment.theme_interactions(experiment.model_input(x), experiment.model_input(x))
    model = experiment.Ridge(alpha=1., solver='lsqr', tol=1e-6).fit(a, target)
    assert np.mean(np.abs(model.predict(b) - target)) < .03
    additive = demo.ridge_pipeline(demo.NUMERIC + demo.INDICATORS, demo.CATEGORICAL, 1.)
    additive.fit(experiment.model_input(x), target)
    assert np.mean(np.abs(additive.predict(experiment.model_input(x)) - target)) > .25
    # Unknown evaluation categories and outliers must not alter the training design matrix.
    first, first_eval = experiment.theme_interactions(experiment.model_input(train), experiment.model_input(evaluation))
    evaluation['party_share_udc'] = 1000
    evaluation['object_domain_1'] = 'another_unseen_theme'
    second, second_eval = experiment.theme_interactions(experiment.model_input(train), experiment.model_input(evaluation))
    np.testing.assert_array_equal(first.toarray(), second.toarray())
    assert first_eval.shape == second_eval.shape
    assert np.isfinite(second_eval.data).all()


def test_latent_predictions_do_not_use_evaluation_results_or_municipality_order():
    train, evaluation, _ = frames()
    mean, predicted, details = experiment.latent_predictions(train, evaluation)
    evaluation['yes_share'] = 1 - evaluation.yes_share
    m2, p2, _ = experiment.latent_predictions(train, evaluation)
    np.testing.assert_array_equal(mean, m2)
    np.testing.assert_array_equal(predicted, p2)
    reordered = evaluation.iloc[::-1]
    _, p3, _ = experiment.latent_predictions(train, reordered)
    np.testing.assert_allclose(predicted, p3[::-1])
    evaluation['municipality_id'] = 'unseen'
    m4, p4, details = experiment.latent_predictions(train, evaluation)
    np.testing.assert_array_equal(m4, p4)
    assert details['unseen_evaluation_municipality_rows_fallback_to_object_mean'] == len(evaluation)


def test_all_models_ignore_heldout_results_and_precomputed_histories():
    train, evaluation, _ = frames()
    outcomes = pd.concat([train, evaluation])[['municipality_id', 'vote_date', 'yes_share']].copy()
    first, details, _ = experiment.fit_window(train, evaluation, outcomes)
    outcomes.loc[outcomes.vote_date.dt.year.eq(2016), 'yes_share'] = 1
    evaluation['yes_share'] = 0
    train[['history_mean_yes', 'history_n_objects', 'history_missing']] = 999
    evaluation[['history_mean_yes', 'history_n_objects', 'history_missing']] = -999
    second, details2, _ = experiment.fit_window(train, evaluation, outcomes)
    np.testing.assert_array_equal(first.raw_prediction, second.raw_prediction)
    assert len(details) == 8  # Nine models, with object_mean sharing the latent fit.
    assert details == details2
    assert first.model.nunique() == 9
    assert first.prediction.between(0, 1).all()
    for _, group in first.groupby('model'):
        assert group.vote_id.tolist() == evaluation.vote_id.tolist()
