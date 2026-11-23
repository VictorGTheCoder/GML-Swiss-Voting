"""Temporal selection and national-vs-municipal anchoring invariants."""

import numpy as np
import pandas as pd
import pytest

from scripts.modeling.poll_anchor import PollAnchoredRegressor, add_poll_features


def municipal_rows(vote_key="6380", vote_date="2021-03-07", baseline=(0.1, 0.4, 0.9)):
    return pd.DataFrame(
        {
            "municipality_id": ["a", "b", "c"],
            "vote_key": [vote_key] * 3,
            "vote_id": [f"object-{vote_key}"] * 3,
            "vote_date": [vote_date] * 3,
            "statpop_pop_total": [100.0, 200.0, 700.0],
            "statpop_share_foreign": [0.0] * 3,
            "statpop_share_0_19": [0.0] * 3,
            "baseline": list(baseline),
            "yes_share": [0.2, 0.3, 0.4],
        }
    )


def poll_rows():
    return pd.DataFrame(
        {
            "vote_key": ["6380", "6380"],
            "vote_date": ["2021-03-07"] * 2,
            "published_at": ["2021-01-29T06:00:00+01:00", "2021-02-24T06:00:00+01:00"],
            "wave": [1, 2],
            "yes_total": [60.0, 50.0],
            "no_total": [30.0, 30.0],
            "undecided": [10.0, 20.0],
        }
    )


class AlreadyFitted:
    def fit(self, *_args, **_kwargs):
        raise AssertionError("The already fitted base model must never be trained")

    def predict(self, frame):
        return frame.baseline.to_numpy().copy()


def enriched(frame=None):
    return add_poll_features(municipal_rows() if frame is None else frame, poll_rows())[0]


def anchored(**kwargs):
    return PollAnchoredRegressor(AlreadyFitted(), **kwargs).fit(enriched())


def test_selects_latest_wave_at_cutoff_and_keeps_all_rows():
    frame = municipal_rows()
    frame.index = [20, 10, 20]
    out, audit = add_poll_features(frame, poll_rows())
    assert out.index.tolist() == frame.index.tolist()
    assert out.poll_wave.tolist() == [2, 2, 2]
    assert out.poll_yes_share.tolist() == [0.5] * 3
    assert out.poll_available.tolist() == [1.0] * 3
    assert (out["poll_yes_share"] + out["poll_no_share"] + out["poll_undecided_share"]).tolist() == [1.0] * 3
    assert audit["poll_objects"] == 1
    assert audit["retained_all_input_rows"]
    assert not audit["strict_forecast_ready"]
    assert "poll_yes_share" not in frame


def test_as_of_and_feature_cutoff_apply_exact_timestamp_boundary():
    frame = municipal_rows().assign(feature_cutoff="2021-02-24T05:00:00Z")
    at_boundary, _ = add_poll_features(frame, poll_rows())
    assert at_boundary.poll_wave.eq(2).all()
    before_boundary, _ = add_poll_features(frame, poll_rows(), as_of="2021-02-24T04:59:59Z")
    assert before_boundary.poll_wave.eq(1).all()
    naive_utc, _ = add_poll_features(frame, poll_rows(), as_of="2021-02-24 05:00:00")
    assert naive_utc.poll_wave.eq(2).all()
    prepublication, audit = add_poll_features(frame, poll_rows(), as_of="2021-01-28")
    assert prepublication.poll_available.eq(0).all()
    assert prepublication.poll_yes_share.isna().all()
    assert audit["objects_without_poll"] == 1


def test_future_wave_is_not_exposed_before_publication():
    frame = municipal_rows("6900", "2026-11-29")
    polls = poll_rows().assign(vote_key="6900", vote_date="2026-11-29")
    polls["published_at"] = ["2026-10-23T06:00:00+02:00", "2026-11-18T06:00:00+01:00"]
    out, _ = add_poll_features(frame, polls, as_of="2026-11-10")
    assert out.poll_wave.eq(1).all()
    later, _ = add_poll_features(frame, polls, as_of="2026-11-23")
    assert later.poll_wave.eq(2).all()


def test_missing_object_has_explicit_missing_poll_and_no_population_filtering():
    frame = pd.concat([municipal_rows(), municipal_rows("9999", "2022-02-13")], ignore_index=True)
    out, audit = add_poll_features(frame, poll_rows())
    assert len(out) == len(frame)
    assert out.poll_available.tolist() == [1.0, 1.0, 1.0, 0.0, 0.0, 0.0]
    assert out.poll_yes_share.iloc[3:].isna().all()
    assert audit["objects_without_poll"] == 1


def test_population_proxy_formula_and_missingness_are_explicit():
    frame = municipal_rows().assign(statpop_share_foreign=[0.2, 0.3, np.nan], statpop_share_0_19=[0.3, 0.1, 0.2])
    out, audit = add_poll_features(frame, poll_rows())
    assert out.poll_population_weight.iloc[:2].tolist() == pytest.approx([56.0, 126.0])
    assert pd.isna(out.poll_population_weight.iloc[2])
    assert audit["population_weight_missing_rows"] == 1
    assert "18/19" in audit["population_proxy"]


@pytest.mark.parametrize("bad_total", [98.0, 102.0, 170.0])
def test_invalid_percentage_sum_fails(bad_total):
    polls = poll_rows().iloc[[0]].copy()
    polls["undecided"] = bad_total - polls.yes_total - polls.no_total
    with pytest.raises(ValueError, match="sum to 100"):
        add_poll_features(municipal_rows(), polls)


@pytest.mark.parametrize("rounding", [-1.0, 1.0])
def test_one_point_source_rounding_is_preserved_not_renormalized(rounding):
    polls = poll_rows().iloc[[0]].copy()
    polls["undecided"] += rounding
    out, audit = add_poll_features(municipal_rows(), polls)
    assert out.poll_yes_share.iloc[0] == 0.6
    assert out.poll_undecided_share.iloc[0] == (10 + rounding) / 100
    assert out[["poll_yes_share", "poll_no_share", "poll_undecided_share"]].iloc[0].sum() == pytest.approx(
        1 + rounding / 100
    )
    assert audit["source_rows_with_rounding"] == 1
    assert audit["selected_rows_with_rounding"] == 1


def test_percentage_total_cannot_disagree_with_detailed_categories():
    polls = poll_rows().assign(yes_certain=30.0, yes_lean=20.0, no_certain=20.0, no_lean=10.0)
    with pytest.raises(ValueError, match="disagrees"):
        add_poll_features(municipal_rows(), polls)


@pytest.mark.parametrize(
    "mutation, error",
    [
        (lambda p: p.assign(vote_date="2021-03-08"), "date mismatch"),
        (lambda p: pd.concat([p, p.iloc[[0]]], ignore_index=True), "duplicate poll"),
        (lambda p: p.assign(published_at="2021-03-07"), "duplicate poll|precede"),
    ],
)
def test_ambiguous_poll_keys_dates_or_publications_fail(mutation, error):
    with pytest.raises(ValueError, match=error):
        add_poll_features(municipal_rows(), mutation(poll_rows()))


def test_different_cutoffs_within_object_and_after_vote_cutoff_fail():
    frame = municipal_rows().assign(feature_cutoff=["2021-02-01", "2021-02-02", "2021-02-01"])
    with pytest.raises(ValueError, match="constant"):
        add_poll_features(frame, poll_rows())
    with pytest.raises(ValueError, match="precede"):
        add_poll_features(frame.assign(feature_cutoff="2021-03-08"), poll_rows())


def test_duplicate_municipality_or_existing_poll_columns_fail():
    with pytest.raises(ValueError, match="Duplicate municipality"):
        add_poll_features(pd.concat([municipal_rows(), municipal_rows().iloc[[0]]]), poll_rows())
    with pytest.raises(ValueError, match="overwrite"):
        add_poll_features(enriched(), poll_rows())


def test_features_are_invariant_to_targets_and_unallowlisted_poll_results():
    first, _ = add_poll_features(municipal_rows(), poll_rows())
    mutated_frame = municipal_rows().assign(yes_share="not a feature", national_yes_share=999, y_eval=-999)
    mutated_source = poll_rows().assign(result_yes_share=1, national_result=0)
    second, _ = add_poll_features(mutated_frame, mutated_source)
    cols = [c for c in first if c.startswith("poll_")]
    pd.testing.assert_frame_equal(first[cols], second[cols])


def test_anchor_hits_weighted_national_target_after_clipping():
    frame = enriched()
    model = anchored()
    components = model.predict_components(frame)
    prediction = components.prediction.to_numpy()
    assert prediction[0] == 0  # Clipping makes a simple mean shift insufficient.
    assert np.average(prediction, weights=frame.poll_population_weight) == pytest.approx(0.6, abs=1e-12)
    assert np.mean(prediction) != pytest.approx(0.6, abs=1e-3)
    assert components.national_baseline_mean.tolist() == pytest.approx([0.72] * 3)
    assert components.national_achieved_mean.tolist() == pytest.approx([0.6] * 3)
    assert np.all((0 <= prediction) & (prediction <= 1))
    assert not model.audit_["base_model_retrained"]


def test_partial_weight_blends_national_means_not_municipality_means():
    frame = enriched()
    model = anchored(weight=0.5)
    assert np.average(model.predict(frame), weights=frame.poll_population_weight) == pytest.approx(0.66, abs=1e-12)
    all_undecided_yes = anchored(undecided_yes_fraction=1.0)
    assert np.average(all_undecided_yes.predict(frame), weights=frame.poll_population_weight) == pytest.approx(
        0.7, abs=1e-12
    )


def test_no_poll_fallback_is_exact_even_for_one_municipality_without_weights():
    frame = enriched(municipal_rows("9999", "2024-03-03", baseline=(-0.2, 1.2, 0.37)))
    frame = frame.drop(
        columns=["poll_population_weight", "statpop_pop_total", "statpop_share_foreign", "statpop_share_0_19"]
    )
    model = anchored()
    assert np.array_equal(model.predict(frame), frame.baseline.to_numpy())
    assert np.array_equal(model.predict(frame.iloc[[0]]), frame.baseline.iloc[[0]].to_numpy())


def test_zero_weight_is_exact_fallback_without_national_batch_requirement():
    frame = enriched().iloc[[2]]
    assert np.array_equal(anchored(weight=0).predict(frame), frame.baseline.to_numpy())


def test_population_guard_rejects_partial_nation_and_single_big_municipality():
    with pytest.raises(ValueError, match="Insufficient population coverage"):
        anchored().predict(enriched().iloc[:2])
    big = enriched().assign(poll_population_weight=[10.0, 20.0, 970.0])
    model = PollAnchoredRegressor(AlreadyFitted()).fit(big)
    with pytest.raises(ValueError, match="one municipality"):
        model.predict(big.iloc[[2]])


def test_population_guard_requires_reference_coverage_not_inflated_current_weights():
    frame = enriched().iloc[:2].copy()
    frame["poll_population_weight"] = [1000.0, 2000.0]
    with pytest.raises(ValueError, match="reference=0.300"):
        anchored().predict(frame)


def test_latest_training_date_reference_does_not_accumulate_obsolete_communes():
    current = enriched()
    old = current.assign(
        vote_key="old",
        vote_id="old",
        vote_date="2019-01-01",
        municipality_id=["retired-a", "retired-b", "retired-c"],
        poll_population_weight=1_000_000.0,
    )
    model = PollAnchoredRegressor(AlreadyFitted()).fit(pd.concat([old, current], ignore_index=True))
    assert model.reference_population_total_ == 1000
    assert model.reference_population_.index.tolist() == ["a", "b", "c"]
    assert model.reference_date_ == pd.Timestamp("2021-03-07")


def test_anchor_ignores_targets_and_preserves_batch_order():
    frame = enriched()
    model = anchored()
    expected = model.predict(frame)
    mutated = frame.assign(yes_share="unused", y_eval=999, national_yes_share=-10)
    assert np.array_equal(model.predict(mutated), expected)
    future = frame.assign(vote_key="future", vote_id="future", vote_date="2026-11-29", baseline=0.8)
    batch = pd.concat([mutated, future], ignore_index=True)
    assert np.array_equal(model.predict(batch)[:3], expected)
    shuffled = mutated.iloc[[2, 0, 1]].copy()
    shuffled.index = [9, 3, 9]
    assert model.predict(shuffled) == pytest.approx(expected[[2, 0, 1]])
    assert model.predict_components(shuffled).index.tolist() == [9, 3, 9]


def test_inconsistent_national_shares_and_availability_fail():
    frame = enriched()
    frame.loc[0, "poll_yes_share"] = 0.55
    with pytest.raises(ValueError, match="constant"):
        anchored().predict(frame)
    with pytest.raises(ValueError, match="constant"):
        anchored().predict(enriched().assign(poll_available=[0, 1, 1]))


@pytest.mark.parametrize(
    "parameter,value",
    [("weight", -1), ("weight", 1.1), ("undecided_yes_fraction", np.nan), ("min_population_fraction", 0)],
)
def test_invalid_anchor_parameters_fail(parameter, value):
    with pytest.raises(ValueError, match=parameter):
        anchored(**{parameter: value})
