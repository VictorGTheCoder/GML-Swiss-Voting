import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone

from scripts.modeling.object_profile_v2 import ObjectProfileRegressor


def training_rows():
    records = []
    for vote in range(8):
        x = vote / 7
        for municipality, offset in [("a", -.1), ("b", -.03), ("c", .04), ("d", .09)]:
            records.append({
                "vote_id": f"train-{vote}", "municipality_id": municipality,
                "vote_date": f"20{10+vote}-01-01", "position": x, "kind": "initiative",
                "yes_share": .3 + .4*x + offset*(.5+x),
            })
    return pd.DataFrame(records)


def model(**kwargs):
    return ObjectProfileRegressor(["position"], ["kind"], alpha=1e-6, **kwargs)


def heldout_rows():
    return pd.DataFrame({
        "vote_id": ["future"]*3, "municipality_id": ["d", "a", "unseen"],
        "vote_date": ["2024-01-01"]*3, "position": [.5]*3,
        "kind": ["initiative"]*3, "yes_share": [.99, .01, .2],
    }, index=[7, 2, 4])


def test_profile_learns_mean_and_local_shape_with_preserved_row_order_and_cold_start():
    fitted = model(dimensions=1).fit(training_rows())
    predictions = fitted.predict(heldout_rows())
    assert predictions == pytest.approx([.59, .4, .5], abs=1e-5)
    diagnostics = fitted.predict_components(heldout_rows())
    assert diagnostics.index.tolist() == [7, 2, 4]
    assert diagnostics.unseen_municipality.tolist() == [False, False, True]
    assert diagnostics.predicted_object_mean.tolist() == pytest.approx([.5]*3, abs=1e-5)
    assert diagnostics.predicted_local_residual.iloc[2] == 0
    assert fitted.audit_["training_objects"] == 8
    assert fitted.audit_["training_rows"] == 32


def test_predictions_ignore_evaluation_targets_and_future_prediction_batch():
    fitted = model(dimensions=3).fit(training_rows())
    heldout = heldout_rows()
    baseline = fitted.predict(heldout)
    changed = heldout.assign(yes_share=["not read", "not read", "not read"],
                             target_share=[999, 999, 999], national_yes_share=[.99]*3)
    assert np.array_equal(baseline, fitted.predict(changed))
    assert np.array_equal(baseline, fitted.predict(heldout.drop(columns="yes_share")))
    future = heldout.assign(vote_id="later", position=20, kind="new category", vote_date="2030-01-01")
    batched = pd.concat([heldout, future], ignore_index=True)
    assert fitted.predict(batched)[:3] == pytest.approx(baseline)
    assert fitted.audit_["training_vote_ids"] == [f"train-{i}" for i in range(8)]


def test_missing_training_cells_use_train_object_mean_and_are_audited():
    train = training_rows().drop(index=0)
    fitted = model(dimensions=20).fit(train)
    assert fitted.audit_["training_matrix_missing_cells"] == 1
    assert fitted.audit_["training_matrix_cells"] == 32
    assert fitted.dimensions_ == 3
    # Reconstruction of the PCA training matrix agrees with the explicit
    # zero residual used only for the missing training municipality/object cell.
    outcomes = train.pivot(index="vote_id", columns="municipality_id", values="yes_share")
    residuals = outcomes.sub(outcomes.mean(axis=1), axis=0).fillna(0).to_numpy()
    reconstructed = fitted.pca_.inverse_transform(fitted.pca_.transform(residuals))
    assert reconstructed == pytest.approx(residuals, abs=1e-12)


@pytest.mark.parametrize("stage", ["fit", "predict"])
def test_object_feature_constancy_rejects_local_feature_or_inconsistent_missingness(stage):
    train = training_rows()
    fitted = model().fit(train)
    if stage == "fit":
        train.loc[0, "position"] = np.nan
        with pytest.raises(ValueError, match="constant within"):
            model().fit(train)
    else:
        heldout = heldout_rows()
        heldout.loc[7, "position"] = .75
        with pytest.raises(ValueError, match="constant within"):
            fitted.predict(heldout)


def test_training_preprocessing_and_pca_are_reproducible_and_y_is_positional():
    train = training_rows()
    target = train.yes_share.to_numpy()
    first = model(dimensions=2).fit(train)
    second = clone(first).fit(train.assign(yes_share="unused"), y=target)
    assert second.components_ == pytest.approx(first.components_)
    assert second.predict(heldout_rows()) == pytest.approx(first.predict(heldout_rows()))
    assert first.preprocessor_.named_transformers_["numeric"].named_steps["imputer"].statistics_[0] == .5


def test_invalid_targets_keys_and_outcome_features_fail_explicitly():
    train = training_rows()
    with pytest.raises(ValueError, match="unique"):
        model().fit(pd.concat([train, train.iloc[[0]]]))
    with pytest.raises(ValueError, match="finite shares"):
        model().fit(train.assign(yes_share=99))
    with pytest.raises(ValueError, match="Outcome/identifier"):
        ObjectProfileRegressor(["yes_share"], []).fit(train)
    with pytest.raises(ValueError, match="multiple voting dates"):
        model().fit(train.assign(vote_date=np.arange(len(train))))


def test_single_object_and_single_municipality_support_zero_components():
    train = training_rows()
    single_object = model(dimensions=5).fit(train[train.vote_id.eq("train-0")])
    assert single_object.dimensions_ == 0
    assert np.isfinite(single_object.predict(heldout_rows())).all()
    single_municipality = model(dimensions=5).fit(train[train.municipality_id.eq("a")])
    assert single_municipality.dimensions_ == 0
    assert single_municipality.predict_components(heldout_rows()).predicted_local_residual.eq(0).all()


@pytest.mark.parametrize("regressor", ["extra_trees", "xgboost", "catboost"])
def test_optional_tree_regressors_produce_finite_predictions_without_target(regressor):
    if regressor in {"xgboost", "catboost"}:
        pytest.importorskip(regressor)
    fitted = model(dimensions=1, model=regressor, n_estimators=12, min_samples_leaf=1).fit(training_rows())
    predictions = fitted.predict(heldout_rows().drop(columns="yes_share"))
    assert np.isfinite(predictions).all()
    assert ((predictions >= 0) & (predictions <= 1)).all()
