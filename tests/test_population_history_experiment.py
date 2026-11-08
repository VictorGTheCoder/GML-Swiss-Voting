"""Historical counts, transition, release selection and held-out label invariants."""
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from scripts.espop import population_history as population
from scripts.integration.build_modeling_dataset import FLAGS
from scripts.modeling import population_history_experiment as experiment


def stocks():
    counts = pd.DataFrame([{'year': y, 'code': c, 'population': n, 'foreign': f}
                           for y in population.YEARS for c, n, f in [('1', 100, 10), ('2', 200, 40)]])
    statpop = pd.DataFrame([{'year': y, 'municipality_id': c, 'pop_total': n, 'pop_foreign': f}
                            for y in range(2010, 2022) for c, n, f in [('0001', 120, 20), ('0002', 240, 50)]])
    return counts, statpop


def inputs():
    counts, statpop = stocks()
    counts.loc[counts.year.eq(1990) & counts.code.eq('1'), 'population'] = 0
    counts.loc[counts.year.eq(1990) & counts.code.eq('1'), 'foreign'] = 0
    annual, _ = population.prepare_population(counts, statpop, {'1', '2'}, {'1', '2'}, [])
    dates = ['1981-06-14', '1982-09-26', '1991-10-01', '2009-01-01', '2012-01-01',
             '2015-01-01', '2020-01-01', '2021-01-01', '2022-01-01']
    rng = np.random.default_rng(51)
    ofs, swiss = [], []
    for i, day in enumerate(dates):
        key = str(1930 + 10 * i)
        swiss.append({'vote_key': key, 'vote_date': pd.Timestamp(day), 'swissvotes_id': str(193 + i),
                      'is_tiebreak_question': False, **{c: str(i % 2) for c in experiment.OBJECT_FIELDS}})
        for municipality in ['0001', '0002']:
            yes = int(rng.integers(10, 90))
            ofs.append({'vote_key': key, 'vote_id': key, 'vote_date': pd.Timestamp(day),
                        'municipality_id': municipality, 'canton': 'ZH', 'votes_yes': yes, 'votes_no': 100 - yes,
                        **dict.fromkeys(FLAGS, False)})
    typologies = pd.DataFrame({'municipality_id': ['0001', '0002'], 'urban_rural': ['1', '2'],
                               'language_region': ['1', '2']})
    return pd.DataFrame(ofs), pd.DataFrame(swiss), typologies, annual


def test_merger_sums_counts_before_ratios_and_statpop_owns_2010():
    counts, statpop = stocks()
    statpop['municipality_id'] = '0010'
    statpop = statpop.groupby(['year', 'municipality_id'], as_index=False)[['pop_total', 'pop_foreign']].sum()
    mutations = [(date(2025, 6, 1), 'merger', {'1': {'10'}, '2': {'10'}})]
    result, exclusions = population.prepare_population(counts, statpop, {'1', '2'}, {'10'}, mutations)
    first = result.loc[result.year.eq(1981)].iloc[0]
    assert first.population_total == 300
    assert first.population_share_foreign == pytest.approx(50 / 300)
    assert first.population_selection_from == pd.Timestamp('1982-09-02')
    transition = result.loc[result.year.eq(2010)].iloc[0]
    assert transition.population_source == 'STATPOP'
    assert transition.population_total == 360
    assert transition.population_share_foreign == pytest.approx(70 / 360)
    assert exclusions.empty


def test_invalid_annual_release_does_not_silently_reuse_an_older_valid_stock():
    ofs, swiss, typologies, annual = inputs()
    table, coverage, rejected, _ = experiment.build_table(ofs, swiss, typologies, annual)
    assert table.vote_date.min() == pd.Timestamp('1982-09-26')
    assert len(rejected.loc[rejected.vote_date.eq('1981-06-14')]) == 2
    bad = rejected.loc[rejected.vote_date.eq('1991-10-01') & rejected.municipality_id.eq('0001')]
    assert len(bad) == 1
    assert bad.population_year.iloc[0] == 1990
    assert bad.exclusion_reason.iloc[0] == 'missing_nonpositive_or_invalid_stock'
    assert coverage.loc[coverage.year.eq(1991), 'excluded_rows'].iloc[0] == 1
    assert table.population_selection_from.le(table.feature_cutoff).all()
    with pytest.raises(ValueError, match='through 2022'):
        experiment.build_table(ofs.assign(vote_date=pd.Timestamp('2023-01-01')), swiss, typologies, annual)


def test_validation_labels_cannot_change_predictions_and_every_model_uses_same_keys():
    ofs, swiss, typologies, annual = inputs()
    first, _, _, _ = experiment.build_table(ofs, swiss, typologies, annual)
    changed = ofs.copy()
    heldout = changed.vote_date.dt.year.ge(2021)
    changed.loc[heldout, ['votes_yes', 'votes_no']] = [1, 99]
    second, _, _, _ = experiment.build_table(changed, swiss, typologies, annual)
    np.testing.assert_allclose(first.history_mean_yes, second.history_mean_yes)
    a, _ = experiment.evaluate(first)
    b, _ = experiment.evaluate(second)
    np.testing.assert_array_equal(a['predictions'].raw_prediction, b['predictions'].raw_prediction)
    assert not a['metrics'].mae_pp.equals(b['metrics'].mae_pp)
    assert a['predictions'].model.nunique() == 12
    assert len(a['contrasts']) == 10
    expected = first.loc[first.partition.eq('validation'), ['municipality_id', 'vote_id', 'vote_date']].reset_index(drop=True)
    for _, frame in a['predictions'].groupby('model'):
        pd.testing.assert_frame_equal(frame[expected.columns].reset_index(drop=True), expected)
    assert set(a['partitions'].regime) == {'recent', 'extended'}
    assert a['partitions'].set_index('regime').loc['extended', 'rows'] > a['partitions'].set_index('regime').loc['recent', 'rows']


def test_population_cache_verifies_its_bytes_before_reuse(tmp_path):
    data = tmp_path / 'counts.csv'
    data.write_text('original')
    manifest = {'sources': [{'file': 'counts.csv', 'sha256': population.sha256(data)}]}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    assert population.collect(tmp_path, tmp_path) == manifest
    data.write_text('changed')
    with pytest.raises(ValueError, match='fingerprint mismatch'):
        population.collect(tmp_path, tmp_path)
