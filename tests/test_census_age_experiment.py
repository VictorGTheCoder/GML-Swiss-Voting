"""Census boundaries, measured denominators and no held-out-label influence."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from scripts.espop import census_age_history as ages
from scripts.modeling import census_age_experiment as experiment


def releases():
    censuses = {}
    for year in ages.CENSUS_DATES:
        censuses[year] = pd.DataFrame({
            'year': [year, year], 'code': ['1', '2'], 'population': [100., 300.], 'foreign': [10., 30.],
            'age_0_19': [20., 90.], 'age_20_39': [30., 60.], 'age_20_64': [60., 150.],
            'age_65_plus': [20., 60.]})
    stats = pd.DataFrame([{'year': y, 'municipality_id': c, 'pop_total': total,
                           'pop_0_19': .2 * total, 'pop_20_39': .3 * total, 'pop_65_plus': .25 * total}
                          for y in range(2010, 2022) for c, total in [('0001', 120), ('0002', 360)]])
    sources = {y: {'1', '2'} for y in ages.CENSUS_DATES}
    return censuses, stats, sources


def test_merger_uses_census_counts_and_own_denominator():
    censuses, stats, sources = releases()
    stats['municipality_id'] = '0010'
    stats = stats.groupby(['year', 'municipality_id'], as_index=False).sum()
    mutation = [(date(2005, 1, 1), 'merger', {'1': {'10'}, '2': {'10'}})]
    result, excluded = ages.prepare_releases(censuses, sources, {'10'}, mutation, stats)
    first = result.loc[result.age_reference_year.eq(1980)].iloc[0]
    assert first.age_denominator == 400
    assert first.age_share_0_19 == pytest.approx(110 / 400)
    assert first.age_share_20_39 == pytest.approx(90 / 400)
    assert first.age_selection_from == pd.Timestamp('1983-01-01')
    assert excluded.empty
    annual = result.loc[result.age_reference_year.eq(2010)].iloc[0]
    assert annual.age_source == 'STATPOP'
    assert annual.age_denominator == 480
    assert annual.age_selection_from == pd.Timestamp('2011-09-02')


def test_new_census_cannot_enter_earlier_votes_and_bad_new_release_is_not_backfilled():
    censuses, stats, sources = releases()
    # A bad 1990 record must prevent silently using the valid 1980 measurement after its replacement.
    censuses[1990].loc[0, 'age_20_39'] = np.nan
    measured, _ = ages.prepare_releases(censuses, sources, {'1', '2'}, [], stats)
    dates = pd.to_datetime(['1982-11-28', '1985-01-01', '1992-11-01', '1993-01-02', '2011-09-03'])
    observations = pd.DataFrame({'municipality_id': ['0001'] * len(dates), 'vote_date': dates,
                                  'vote_id': [str(i) for i in range(len(dates))],
                                  'feature_cutoff': dates - pd.Timedelta(days=1)})
    joined, _ = experiment.attach_ages(observations, measured)
    assert pd.isna(joined.age_reference_year.iloc[0])
    assert joined.age_missing.iloc[0]
    assert joined.age_reference_year.iloc[1:3].tolist() == [1980, 1980]
    assert joined.age_reference_year.iloc[3] == 1990
    assert joined.age_missing.iloc[3] and pd.isna(joined.age_share_20_39.iloc[3])
    assert joined.age_reference_year.iloc[4] == 2010
    assert joined.age_source.iloc[4] == 'STATPOP'
    assert joined.age_measurement_age_years.iloc[1] > 4
    # Perturb all newer censuses; earlier rows must be unchanged.
    censuses[1990]['age_0_19'] = [10., 30.]
    censuses[2000]['age_0_19'] = [10., 30.]
    changed, _ = ages.prepare_releases(censuses, sources, {'1', '2'}, [], stats)
    before, _ = experiment.attach_ages(observations.iloc[:3], changed)
    pd.testing.assert_frame_equal(joined.iloc[:3][ages.AGE_SHARES], before[ages.AGE_SHARES])


def test_unproven_split_does_not_create_age_measurements():
    censuses, stats, sources = releases()
    mutations = [(date(2005, 1, 1), 'split', {'1': {'1', '3'}})]
    result, exclusions = ages.prepare_releases(censuses, sources, {'1', '2', '3'}, mutations, stats)
    census = result.loc[result.age_source.eq('RFP')]
    assert not census.loc[census.municipality_id.isin(['0001', '0003']), 'age_valid'].any()
    assert 'unproven_split_or_transfer' in set(exclusions.reason)


def modeling_table():
    rng = np.random.default_rng(84)
    dates = pd.to_datetime(np.repeat(['1985-01-01', '1995-01-01', '2005-01-01',
                                      '2012-01-01', '2020-01-01', '2021-01-01', '2022-01-01'], 2))
    table = pd.DataFrame({c: rng.uniform(size=len(dates)) for c in experiment.base.HISTORY + experiment.base.POPULATION})
    for c in experiment.base.CATEGORICAL:
        table[c] = np.repeat(['a', 'b', 'a', 'b', 'a', 'new', 'new'], 2)
    table['municipality_id'] = ['0001', '0002'] * 7
    table['vote_id'] = np.repeat([str(i) for i in range(7)], 2)
    table['vote_date'] = dates
    table['yes_share'] = rng.uniform(size=len(dates))
    table['has_valid_population'] = True
    table['feature_cutoff'] = dates - pd.Timedelta(days=1)
    censuses, stats, sources = releases()
    measured, _ = ages.prepare_releases(censuses, sources, {'1', '2'}, [], stats)
    return experiment.attach_ages(table, measured)[0]


def test_eight_models_use_same_keys_and_ignore_heldout_labels():
    table = modeling_table()
    a, _ = experiment.evaluate(table)
    changed = table.copy()
    changed.loc[changed.vote_date.dt.year.ge(2021), 'yes_share'] = 0
    b, _ = experiment.evaluate(changed)
    np.testing.assert_array_equal(a['predictions'].raw_prediction, b['predictions'].raw_prediction)
    assert not a['metrics'].mae_pp.equals(b['metrics'].mae_pp)
    assert a['predictions'].model.nunique() == 8
    assert a['predictions'].prediction.between(0, 1).all()
    keys = ['municipality_id', 'vote_id', 'vote_date']
    expected = table.loc[table.vote_date.dt.year.ge(2021), keys].reset_index(drop=True)
    for _, frame in a['predictions'].groupby('model'):
        pd.testing.assert_frame_equal(frame[keys].reset_index(drop=True), expected)
    assert len(a['contrasts']) == 8
    with pytest.raises(ValueError, match='through 2022'):
        experiment.evaluate(table.assign(vote_date=pd.Timestamp('2023-01-01')))
