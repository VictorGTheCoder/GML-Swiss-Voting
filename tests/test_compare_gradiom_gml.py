"""The head-to-head comparator never scores different populations."""
import pandas as pd
import pytest

from scripts.modeling.compare_gradiom_gml import MODELS, paired_metrics


def test_paired_population_and_gain():
    e = pd.DataFrame({"vote_id":["1","1"], "municipality_id":["0001","0002"],
                      "vote_date":["2022-01-01"]*2, "official_yes_share":[.4,.6],
                      "gradiom_prediction":[.3,.5]})
    g = e[["vote_id","municipality_id","vote_date"]].copy()
    for name in MODELS[1:]:
        g[name] = [.4,.6]
    _, _, scores = paired_metrics(e,g)
    assert scores[0]["mae_pp"] == pytest.approx(10.)
    assert scores[1]["gain_vs_gradiom"] == pytest.approx(10.)
    with pytest.raises(ValueError,match="missing"):
        paired_metrics(e,g.iloc[:1])
