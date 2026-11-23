import numpy as np
import pandas as pd
import pytest

from scripts.modeling.object_enrichment_v3 import (
    build_object_features,
    encode_domains,
    fit_domain_vocabulary,
    number,
)


def inputs():
    objects = pd.DataFrame({"vote_id": ["a", "b"], "vote_key": ["1000", "1010"],
                            "vote_date": pd.to_datetime(["2020-03-01", "2020-09-27"])})
    source = objects[["vote_key", "vote_date"]].assign(
        **{"p-eco": [1, 5], "p-sgb": [2, 9999], "rechtsform": [3, 1],
           "unter_g": ["120’000", "0"], "unter-quorum": ["100'000", "0"],
           "sammeltempo": [400, 0], "dat-submit": ["01.01.2019", "0"],
           "dat-success": ["01.03.2019", "0"], "dat-parl": ["01.09.2019", "01.03.2020"],
           "d1e1": [1, 2], "d2e1": [2, 1], "d3e1": [np.nan, np.nan],
           "d1e2": [11, 22], "d1e3": [111, 222], "dep": [2, 5], "anzahl": [2, 3]})
    return objects, source


def test_exact_keys_dates_and_target_blind_extraction():
    objects, source = inputs()
    a, audit = build_object_features(objects, source)
    b, _ = build_object_features(objects.assign(yes_share=[0, 1]), source.assign(**{"volkja-proz": [99, 1]}))
    pd.testing.assert_frame_equal(a, b)
    assert audit["post_vote_fields_read"] is False
    assert audit["strict_forecast_ready"] is False
    assert a.extra_stakeholder_eco.tolist() == ["yes", "free_vote"]
    assert a.extra_stakeholder_sgb.tolist() == ["no", "not_existing"]
    assert a.extra_stakeholder_sbv.isna().all()


def test_signatures_and_dates_respect_observed_pre_vote_events():
    objects, source = inputs()
    result, _ = build_object_features(objects, source)
    assert result.extra_signature_quorum_ratio.iloc[0] == pytest.approx(1.2)
    assert result.extra_log_valid_signatures.iloc[0] == pytest.approx(np.log1p(120000))
    assert result.extra_signature_status.tolist() == ["date_gated_observation", "not_applicable"]
    assert np.isnan(result.extra_signature_quorum_ratio.iloc[1])
    source.loc[0, "dat-success"] = "02.03.2020"
    later, _ = build_object_features(objects, source)
    assert np.isnan(later.extra_log_valid_signatures.iloc[0])
    assert later.extra_signature_status.iloc[0] == "missing_or_not_yet_certified"


@pytest.mark.parametrize("change", ["duplicate", "date", "missing", "invalid_code", "nonnumeric", "infinite"])
def test_bad_source_contract_fails(change):
    objects, source = inputs()
    if change == "duplicate":
        source = pd.concat([source, source.iloc[[0]]])
    elif change == "date":
        source.loc[0, "vote_date"] += pd.Timedelta(days=1)
    elif change == "missing":
        source = source.iloc[[1]]
    elif change == "invalid_code":
        source.loc[0, "p-eco"] = 42
    else:
        source["p-eco"] = source["p-eco"].astype(object)
        source.loc[0, "p-eco"] = "mistyped" if change == "nonnumeric" else "inf"
    with pytest.raises(ValueError):
        build_object_features(objects, source)


def test_multilabel_domains_ignore_slot_order_and_future_vocabulary():
    objects, source = inputs()
    features, _ = build_object_features(objects, source)
    assert features.extra_domain_tokens_1.tolist() == ["1|2", "1|2"]
    vocab = fit_domain_vocabulary(features.iloc[[0]])
    encoded = encode_domains(features, vocab)
    assert not any("222" in name for name in encoded)
    assert encoded.extra_domain_present_3_111.tolist() == [1, 0]
    assert encoded.extra_domain_present_1_1.tolist() == [1, 1]


def test_grouping_numeric_parser_does_not_invent_nonfinite_values():
    observed = number(pd.Series(["100’000", "50'000", ".", "0", "inf"]))
    assert observed.iloc[:2].tolist() == [100000, 50000]
    assert np.isnan(observed.iloc[2]) and observed.iloc[3] == 0 and np.isnan(observed.iloc[4])
