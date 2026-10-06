import pandas as pd
import matplotlib

from analysis.swiss_voting_feasibility import add_historical_features, build_temporal_vote_split, join_prior_year_population


def test_plot_backend_is_headless_for_reproducible_cli_runs():
    assert matplotlib.get_backend().lower() == "agg"


def test_temporal_split_keeps_each_vote_in_one_partition():
    rows = pd.DataFrame(
        {
            "vote_id": ["v1", "v1", "v2", "v2", "v3", "v3", "v4", "v4"],
            "vote_date": pd.to_datetime(
                ["2015-01-01", "2015-01-01", "2016-01-01", "2016-01-01", "2017-01-01", "2017-01-01", "2018-01-01", "2018-01-01"]
            ),
        }
    )

    split = build_temporal_vote_split(rows, train_fraction=0.5, validation_fraction=0.25)

    assert split.groupby("vote_id")["split"].nunique().eq(1).all()
    assert set(split.loc[split.split == "train", "vote_id"]) == {"v1", "v2"}
    assert set(split.loc[split.split == "validation", "vote_id"]) == {"v3"}
    assert set(split.loc[split.split == "test", "vote_id"]) == {"v4"}


def test_historical_features_only_use_strictly_earlier_votes():
    rows = pd.DataFrame(
        {
            "commune_id": ["a", "a", "a", "b", "b"],
            "vote_id": ["v1", "v2", "v3", "v1", "v2"],
            "vote_date": pd.to_datetime(["2020-01-01", "2020-06-01", "2021-01-01", "2020-01-01", "2020-06-01"]),
            "yes_share": [0.2, 0.8, 0.4, 0.1, 0.3],
            "turnout": [0.4, 0.6, 0.5, 0.5, 0.7],
        }
    )

    result = add_historical_features(rows)

    commune_a = result.loc[result.commune_id == "a"].sort_values("vote_date")
    assert commune_a.iloc[0].historical_yes_mean != commune_a.iloc[0].historical_yes_mean  # NaN: no history
    assert commune_a.iloc[1].historical_yes_mean == 0.2
    assert commune_a.iloc[2].historical_yes_mean == 0.5
    assert commune_a.iloc[2].historical_turnout_mean == 0.5


def test_population_join_uses_prior_year_for_multiple_communes():
    votes = pd.DataFrame({
        "commune_id": ["a", "b", "a", "b"], "year": [2011, 2011, 2013, 2013],
        "vote_date": pd.to_datetime(["2011-02-01", "2011-02-01", "2013-02-01", "2013-02-01"]),
    })
    population = pd.DataFrame({
        "commune_id": ["a", "b"], "population_year": [2010, 2010], "population": [100, 200],
    })

    joined = join_prior_year_population(votes, population)

    assert joined.population.tolist() == [100, 200, 100, 200]
