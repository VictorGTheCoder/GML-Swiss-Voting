import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone

from scripts.modeling.poll_anchor import PollAnchoredRegressor
from scripts.modeling.prototype_profile_v3 import PrototypeProfileRegressor


def training_rows():
    rows = []
    for vote in range(8):
        position = vote / 7
        for municipality, offset in [("a", -.1), ("b", -.03), ("c", .04), ("d", .09)]:
            rows.append({
                "vote_id": f"train-{vote}", "municipality_id": municipality,
                "vote_date": f"20{10 + vote}-01-01", "position": position,
                "kind": "initiative", "yes_share": .3 + .4 * position + offset * (.5 + position),
            })
    return pd.DataFrame(rows)


def heldout_rows():
    return pd.DataFrame({
        "vote_id": ["future"] * 3, "municipality_id": ["d", "a", "unseen"],
        "vote_date": ["2024-01-01"] * 3, "position": [.5] * 3,
        "kind": ["initiative"] * 3, "yes_share": [.99, .01, .2],
    }, index=[7, 2, 4])


def model(**kwargs):
    return PrototypeProfileRegressor(["position"], ["kind"], alpha=1e-6, **kwargs)


def test_full_rank_prototypes_recover_known_response_and_unknown_commune_uses_mean():
    fitted = model(n_prototypes=4, dimensions=3).fit(training_rows())
    components = fitted.predict_components(heldout_rows())
    assert fitted.predict(heldout_rows()) == pytest.approx([.59, .4, .5], abs=1e-5)
    assert components.index.tolist() == [7, 2, 4]
    assert components.unseen_municipality.tolist() == [False, False, True]
    assert components.predicted_local_residual.iloc[2] == 0
    assert components.predicted_object_mean.tolist() == pytest.approx([.5] * 3, abs=1e-5)


def test_memberships_are_probabilities_and_basis_is_centred_orthonormal():
    fitted = model(n_prototypes=3).fit(training_rows())
    assert fitted.memberships_.shape == (4, 3)
    assert np.all(fitted.memberships_ > 0)
    assert fitted.memberships_.sum(axis=1) == pytest.approx(np.ones(4), abs=1e-14)
    assert fitted.dimensions_ == 2
    assert fitted.components_.sum(axis=1) == pytest.approx(np.zeros(2), abs=1e-12)
    assert fitted.components_ @ fitted.components_.T == pytest.approx(np.eye(2), abs=1e-12)
    assert fitted.residual_mean_.sum() == pytest.approx(0, abs=1e-12)
    full_batch = pd.DataFrame({
        "vote_id": ["future"] * 4, "municipality_id": fitted.municipalities_,
        "position": [.25] * 4, "kind": ["initiative"] * 4,
    })
    assert fitted.predict_components(full_batch).predicted_local_residual.mean() == pytest.approx(0, abs=1e-12)


def test_predictions_ignore_targets_future_objects_and_future_municipalities():
    fitted = model().fit(training_rows())
    heldout = heldout_rows()
    baseline = fitted.predict(heldout)
    memberships = fitted.memberships_.copy()
    centres = fitted.clusterer_.cluster_centers_.copy()
    poisoned = heldout.assign(yes_share="must not read", national_yes_share=999, target_share=-999)
    assert np.array_equal(fitted.predict(poisoned), baseline)
    assert np.array_equal(fitted.predict(heldout.drop(columns="yes_share")), baseline)
    later = heldout.assign(vote_id="later", position=20, kind="new", vote_date="2030-01-01")
    assert fitted.predict(pd.concat([poisoned, later], ignore_index=True))[:3] == pytest.approx(baseline)
    assert np.array_equal(fitted.memberships_, memberships)
    assert np.array_equal(fitted.clusterer_.cluster_centers_, centres)
    assert fitted.clusterer_.n_features_in_ == 8
    assert fitted.audit_["training_vote_ids"] == [f"train-{i}" for i in range(8)]
    assert fitted.municipalities_.tolist() == ["a", "b", "c", "d"]


def test_clone_and_positional_y_are_reproducible_without_reading_frame_target():
    train = training_rows()
    first = model(n_prototypes=3, temperature=.1).fit(train)
    second = clone(first).fit(train.assign(yes_share="unused"), y=train.yes_share.to_numpy())
    assert second.memberships_ == pytest.approx(first.memberships_, abs=1e-14)
    assert second.components_ == pytest.approx(first.components_, abs=1e-14)
    assert second.predict(heldout_rows()) == pytest.approx(first.predict(heldout_rows()))
    assert first.temperature_ == .1
    assert first.preprocessor_.named_transformers_["numeric"].named_steps["imputer"].statistics_[0] == .5


def test_missing_matrix_cells_and_degenerate_profiles_are_explicit():
    train = training_rows().drop(index=0)
    fitted = model(n_prototypes=20, dimensions=20).fit(train)
    assert fitted.audit_["training_matrix_missing_cells"] == 1
    assert fitted.audit_["training_matrix_cells"] == 32
    assert fitted.n_prototypes_ == 4
    expected = train.pivot(index="vote_id", columns="municipality_id", values="yes_share")
    residuals = expected.sub(expected.mean(axis=1), axis=0).fillna(0)
    assert fitted.residual_mean_ == pytest.approx(residuals.mean(axis=0).to_numpy())
    assert np.isfinite(fitted.predict(heldout_rows())).all()
    identical = model().fit(training_rows().assign(yes_share=.5))
    assert identical.n_prototypes_ == 1
    assert identical.dimensions_ == 0
    assert identical.memberships_ == pytest.approx(np.ones((4, 1)))
    assert identical.predict(heldout_rows()) == pytest.approx([.5] * 3)


def test_single_object_or_municipality_supports_no_spatial_coefficients():
    train = training_rows()
    for subset in [train[train.vote_id.eq("train-0")], train[train.municipality_id.eq("a")]]:
        fitted = model().fit(subset)
        assert fitted.dimensions_ == 0
        assert np.isfinite(fitted.predict(heldout_rows())).all()


def test_feature_and_target_guards_are_shared_with_v2():
    train = training_rows()
    with pytest.raises(ValueError, match="unique"):
        model().fit(pd.concat([train, train.iloc[[0]]]))
    with pytest.raises(ValueError, match="finite shares"):
        model().fit(train.assign(yes_share=99))
    with pytest.raises(ValueError, match="Outcome/identifier"):
        PrototypeProfileRegressor(["yes_share"], []).fit(train)
    with pytest.raises(ValueError, match="constant within"):
        model().fit(train.assign(position=np.arange(len(train))))
    with pytest.raises(ValueError, match="multiple voting dates"):
        model().fit(train.assign(vote_date=np.arange(len(train))))


@pytest.mark.parametrize("parameters", [
    {"n_prototypes": 0}, {"n_prototypes": 2.5}, {"dimensions": -1},
    {"temperature": 0}, {"temperature": np.nan}, {"temperature": np.inf}, {"temperature": "tuned"},
])
def test_invalid_parameters_fail(parameters):
    with pytest.raises(ValueError):
        model(**parameters).fit(training_rows())


def test_poll_anchor_uses_fitted_prototype_model_without_targets():
    train = training_rows().assign(poll_population_weight=1.0)
    train["vote_key"] = train.vote_id
    base = model().fit(train)
    anchored = PollAnchoredRegressor(base).fit(train)
    batch = pd.DataFrame({
        "vote_id": ["future"] * 4, "vote_key": ["future"] * 4,
        "municipality_id": ["a", "b", "c", "d"],
        "vote_date": ["2024-01-01"] * 4, "position": [.5] * 4, "kind": ["initiative"] * 4,
        "poll_available": [1.0] * 4, "poll_yes_share": [.6] * 4,
        "poll_no_share": [.3] * 4, "poll_undecided_share": [.1] * 4,
        "poll_population_weight": [1.0] * 4,
    })
    prediction = anchored.predict(batch)
    assert prediction.mean() == pytest.approx(.65, abs=1e-12)
    assert not anchored.audit_["base_model_retrained"]


def test_xgboost_head_runs_with_same_parameters_as_v2():
    pytest.importorskip("xgboost")
    fitted = model(model="xgboost", n_estimators=8, max_depth=2, n_prototypes=3).fit(training_rows())
    predictions = fitted.predict(heldout_rows().drop(columns="yes_share"))
    assert np.isfinite(predictions).all()
    assert np.all((predictions >= 0) & (predictions <= 1))
