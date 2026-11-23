import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone

from scripts.modeling.residual_voting_model import HierarchicalResidualRegressor


def training_rows():
    records = []
    for vote in range(8):
        stance = vote / 7
        for municipality, local in [("a", -.15), ("b", -.05), ("c", .05), ("d", .15)]:
            records.append({
                "vote_id": f"train-{vote}", "municipality_id": municipality,
                "vote_date": f"20{10+vote}-06-01", "stance": stance, "kind": "initiative",
                "local_signal": local, "region": "common", "yes_share": .3 + .4*stance + local,
            })
    return pd.DataFrame(records)


def model(**kwargs):
    options = {"mean_model": "ridge", "mean_params": {"alpha": 1e-6},
               "local_model": "ridge", "local_params": {"alpha": 1e-6}}
    options.update(kwargs)
    return HierarchicalResidualRegressor(["stance"], ["kind"], ["local_signal"], ["region"], **options)


def heldout_rows():
    return pd.DataFrame({
        "vote_id": ["new"]*3, "municipality_id": ["a", "d", "unseen"],
        "vote_date": ["2024-01-01"]*3, "stance": [.5]*3, "kind": ["initiative"]*3,
        "local_signal": [-.15, .15, -.1], "region": ["common"]*3,
        "yes_share": [0., 1., .7],
    }, index=[5, 2, 8])


def test_signed_local_residual_and_unknown_municipality_covariate_prediction():
    fitted = model().fit(training_rows())
    details = fitted.predict_components(heldout_rows())
    assert details.index.tolist() == [5, 2, 8]
    assert details.predicted_object_mean.tolist() == pytest.approx([.5]*3, abs=1e-6)
    assert details.predicted_local_residual_raw.tolist() == pytest.approx([-.15, .15, -.1], abs=1e-6)
    assert details.prediction.tolist() == pytest.approx([.35, .65, .4], abs=1e-6)
    assert details.unseen_municipality.tolist() == [False, False, True]
    assert fitted.audit_["local_target_min"] < 0 < fitted.audit_["local_target_max"]
    assert fitted.audit_["local_target_max_abs_object_mean"] < 1e-15
    assert fitted.audit_["training_objects"] == 8
    assert fitted.audit_["local_training_objects"] == 6


def test_evaluation_targets_and_unrelated_future_batch_cannot_change_predictions_or_fit():
    fitted = model().fit(training_rows())
    evaluation = heldout_rows()
    expected = fitted.predict(evaluation)
    changed = evaluation.assign(yes_share="unused", target_share=999, national_yes_share=999)
    np.testing.assert_allclose(expected, fitted.predict(changed))
    np.testing.assert_allclose(expected, fitted.predict(evaluation.drop(columns="yes_share")))
    future = evaluation.assign(vote_id="later", vote_date="2030-01-01", stance=1.2, region="unseen")
    np.testing.assert_allclose(expected, fitted.predict(pd.concat([evaluation, future], ignore_index=True))[:3])
    np.testing.assert_allclose(expected, fitted.predict(evaluation))
    assert fitted.audit_["training_objects"] == 8


def test_default_batch_invariance_and_explicit_centering_population_dependence():
    evaluation = heldout_rows()
    raw = model().fit(training_rows())
    full_raw = raw.predict(evaluation)
    singleton_raw = raw.predict(evaluation.iloc[[0]])
    assert singleton_raw[0] == pytest.approx(full_raw[0])
    centered = model(center_local_predictions=True).fit(training_rows())
    details = centered.predict_components(evaluation)
    assert details.predicted_local_residual.mean() == pytest.approx(0, abs=1e-15)
    assert details.raw_prediction.mean() == pytest.approx(details.predicted_object_mean.iloc[0])
    single = centered.predict_components(evaluation.iloc[[0]])
    assert single.predicted_local_residual.iloc[0] == 0
    assert single.raw_prediction.iloc[0] == pytest.approx(.5, abs=1e-6)
    assert single.raw_prediction.iloc[0] != pytest.approx(details.raw_prediction.iloc[0])


def test_object_profile_stored_spatial_mean_is_never_added_again():
    fitted = model().fit(training_rows())
    expected = fitted.predict(heldout_rows())
    # The wrapped object model learns a historical spatial mean even at rank 0.
    # It is irrelevant here: the covariate regressor owns the entire local term.
    fitted.mean_estimator_.residual_mean_[:] = 100
    np.testing.assert_allclose(expected, fitted.predict(heldout_rows()))


def test_cloning_and_explicit_positional_targets_are_reproducible():
    training = training_rows()
    first = model().fit(training)
    second = clone(first).fit(training.assign(yes_share="not read"), y=training.yes_share.to_numpy())
    np.testing.assert_allclose(first.predict(heldout_rows()), second.predict(heldout_rows()), rtol=0, atol=1e-12)


def test_future_local_category_is_not_fitted_and_only_final_sum_is_clipped():
    fitted = model().fit(training_rows())
    future = heldout_rows().assign(region="new region")
    categories = fitted.local_estimator_.named_steps["prepare"].named_transformers_["categorical"].categories_
    fitted.predict(future)
    assert list(categories[0]) == ["common"]
    extreme = heldout_rows().assign(local_signal=[-10., 10., 0.])
    details = fitted.predict_components(extreme)
    assert details.predicted_local_residual_raw.iloc[0] < -1
    assert details.predicted_local_residual_raw.iloc[1] > 1
    assert details.prediction.tolist() == pytest.approx([0., 1., .5], abs=1e-6)


def test_invalid_feature_keys_dates_and_empty_local_training_fail():
    train = training_rows()
    with pytest.raises(ValueError, match="Outcome/identifier"):
        HierarchicalResidualRegressor(["stance"], [], ["yes_share"], []).fit(train)
    with pytest.raises(ValueError, match="unique"):
        model().fit(pd.concat([train, train.iloc[[0]]]))
    with pytest.raises(ValueError, match="No local training rows"):
        model(local_train_start="2030-01-01").fit(train)
    with pytest.raises(ValueError, match="vote_date"):
        model().fit(train.drop(columns="vote_date"))


@pytest.mark.parametrize("local_kind,params", [
    ("xgboost", {"n_estimators": 20, "max_depth": 2, "reg_lambda": 1.}),
    ("catboost", {"iterations": 20, "depth": 2, "l2_leaf_reg": 1.}),
])
def test_native_tree_local_regressors_accept_negative_residual_targets(local_kind, params):
    pytest.importorskip(local_kind)
    fitted = model(local_model=local_kind, local_params=params).fit(training_rows())
    details = fitted.predict_components(heldout_rows().drop(columns="yes_share"))
    assert np.isfinite(details.prediction).all()
    assert details.predicted_local_residual_raw.iloc[0] < 0
    assert details.predicted_local_residual_raw.iloc[1] > 0
