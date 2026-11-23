"""Behavioral checks for the chronological V2 experiment boundary."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts.modeling.experiment_control_v2 import date_bootstrap
from scripts.modeling.municipal_v2 import (
    BASE_CATEGORICAL,
    BASE_NUMERIC,
    PROTOCOL,
    fit_model,
    freeze_history,
    metrics,
    training_weights,
    validate_config,
    windows,
)


def history_frame():
    return pd.DataFrame({
        "municipality_id": ["a", "a", "a", "b", "b", "b"],
        "vote_id": ["1", "2", "3", "1", "2", "3"],
        "vote_date": pd.to_datetime(["2014-01-01", "2015-01-01", "2015-01-01"] * 2),
        "yes_share": [.2, .4, .6, .1, .2, .3],
        "history_n_objects": [0., 1., 1., 0., 1., 1.],
        "history_mean_yes": [np.nan, .2, .2, np.nan, .1, .1],
    })


def test_freeze_history_uses_all_last_date_objects_and_no_evaluation_labels():
    train = history_frame()
    evaluation = pd.DataFrame({"municipality_id": ["b", "a", "z"], "vote_id": ["4"] * 3,
        "vote_date": pd.to_datetime(["2016-01-01"] * 3), "yes_share": [.99, .99, .99],
        "history_mean_yes": [999.] * 3, "history_n_objects": [999.] * 3}, index=[9, 4, 18])
    first = freeze_history(train, evaluation)
    changed = evaluation.copy()
    changed["yes_share"] = .001
    second = freeze_history(train, changed)
    np.testing.assert_allclose(first.history_mean_yes[:2], [.2, .4])
    np.testing.assert_allclose(first.history_n_objects[:2], [3., 3.])
    assert pd.isna(first.history_mean_yes.iloc[2])
    assert first.index.tolist() == evaluation.index.tolist()
    pd.testing.assert_series_equal(first.history_mean_yes, second.history_mean_yes)


def test_freeze_history_rejects_same_day_training():
    frame = history_frame()
    with pytest.raises(ValueError, match="precede"):
        freeze_history(frame, frame.tail(1))


def test_score_is_macro_over_objects_not_population_of_rows():
    frame = pd.DataFrame({"municipality_id": ["a", "b", "c", "a"],
        "vote_id": ["1", "1", "1", "2"],
        "vote_date": pd.to_datetime(["2020-01-01"] * 3 + ["2020-02-01"]),
        "yes_share": [.5] * 4, "prediction": [.5, .5, .5, .1]})
    scored, _, _ = metrics(frame)
    assert scored["macro_object_mae_pp"] == pytest.approx(20.)
    assert scored["row_mae_pp"] == pytest.approx(10.)
    assert scored["within_4pp_share"] == .75
    interval = date_bootstrap(frame, replicates=100)
    assert interval["unit"] == "whole voting date"
    assert interval["dates"] == 2


def test_objects_receive_equal_training_mass_despite_missing_communes():
    train = history_frame().iloc[[0, 1, 2, 4, 5]].copy()
    train["weight"] = training_weights(train, {})
    totals = train.groupby("vote_id").weight.sum()
    np.testing.assert_allclose(totals, totals.iloc[0])


@pytest.mark.parametrize("bad", [np.nan, np.inf, -0.1, 1.1])
def test_metrics_reject_missing_or_impossible_values(bad):
    frame = history_frame().assign(prediction=bad)
    with pytest.raises(ValueError, match="finite"):
        metrics(frame)


def test_declared_windows_never_split_a_date_or_share_future_training():
    frames = []
    for year in range(2012, 2023):
        sample = history_frame().iloc[:2].copy()
        sample["vote_date"] = pd.Timestamp(f"{year}-06-01")
        sample["vote_id"] = [f"{year}a", f"{year}b"]
        frames.append(sample)
    data = pd.concat(frames, ignore_index=True)
    seen = set()
    for _, train, evaluation in windows(data, json.loads(PROTOCOL.read_text()), pd.Timestamp("2012-01-01")):
        assert train.vote_date.max() < evaluation.vote_date.min()
        assert not set(evaluation.vote_date) & seen
        assert evaluation.groupby("vote_date").vote_id.nunique().eq(2).all()
        seen.update(evaluation.vote_date)
    assert len(seen) == 7


@pytest.mark.parametrize("family,params", [
    ("ridge", {"alpha": 10.}),
    ("xgboost", {"n_estimators": 4, "max_depth": 2, "objective": "reg:squarederror"}),
    ("catboost", {"iterations": 4, "depth": 2, "loss_function": "RMSE"}),
])
def test_real_estimators_predict_without_outcomes_or_fitting_future_categories(family, params):
    if family in ("xgboost", "catboost"):
        pytest.importorskip(family)
    rows = []
    for obj in range(6):
        for municipality in range(4):
            row = dict.fromkeys(BASE_NUMERIC, 0.2 + 0.01 * municipality)
            row.update(dict.fromkeys(BASE_CATEGORICAL, "known"))
            row.update(municipality_id=str(municipality), vote_id=str(obj),
                       vote_date=pd.Timestamp(f"201{obj}-06-01"), yes_share=.2 + .05 * obj,
                       history_n_objects=float(obj))
            rows.append(row)
    train = pd.DataFrame(rows)
    manifest = {"political": {"numeric_features": [], "categorical_features": []},
                "direction": {"numeric_features": []}}
    fitted = fit_model(train, {"name": "test", "model": family, "params": params,
                               "select_k": "all" if family == "catboost" else 12}, manifest)
    future = train.iloc[:4].drop(columns="yes_share").copy()
    future["object_domain_1"] = "unseen"
    before = fitted.predict(future)
    changed = future.assign(yes_share=1.)
    after = fitted.predict(changed)
    np.testing.assert_allclose(before, after)
    assert np.isfinite(before).all()
    assert ((before >= 0) & (before <= 1)).all()


@pytest.mark.parametrize("config", [
    {"model": "profile", "select_k": 10},
    {"model": "hierarchical", "half_life_years": 8},
    {"model": "catboost", "select_k": 10},
    {"model": "xgboost", "blocks": "typo"},
    {"model": "poll_anchor", "base": {"model": "profile", "train_start": "1990-01-01"}},
])
def test_ignored_or_history_truncating_settings_are_rejected(config):
    with pytest.raises(ValueError):
        validate_config(config)


def test_poll_wrapper_preserves_declared_base_history():
    validate_config({"model": "poll_anchor", "train_start": "1981-01-01",
                     "base": {"model": "profile", "train_start": "1990-01-01"}})
