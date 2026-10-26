"""Publication-safe municipal history aggregated once per forecast/date/partition context."""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_historical_features(rows, config):
    """Return shared local history and the admissible training-only global mean.

    A missing global mean remains NaN so baselines abstain. The regression feature
    uses the separately documented 0.5 cold-start prior only in that case.
    """
    result = pd.DataFrame(index=rows.index,columns=['municipal_history','history_missing','training_mean'],dtype=float)
    known = (rows.result_available_at.notna() & rows.result_availability_evidence.notna()
             & rows.result_availability_evidence.astype('string').str.strip().ne('').fillna(False))
    history = rows.loc[known].groupby(
        ['voting_date','result_available_at','partition','municipality_id','geography_id'],sort=False).target_share.agg(['sum','count']).reset_index()
    refit = config.mode == 'final_test' and config.refit_train_validation
    contexts = ['voting_date','forecast_at','partition']
    for (date,cutoff,partition),targets in rows.groupby(contexts,sort=False):
        partitions = ['train','validation'] if refit or (config.history_policy == 'rolling' and partition != 'train') else ['train']
        if config.history_policy == 'rolling' and partition == 'test':
            partitions.append('test')
        available = history.voting_date.lt(date) & history.result_available_at.le(cutoff)
        training = history.loc[available & history.partition.eq('train')]
        training_mean = float(training['sum'].sum()/training['count'].sum()) if not training.empty else np.nan
        local = history.loc[available & history.partition.isin(partitions)].groupby(
            ['municipality_id','geography_id'],sort=False)[['sum','count']].sum()
        keys = pd.MultiIndex.from_frame(targets[['municipality_id','geography_id']])
        means = (local['sum']/local['count']).reindex(keys).to_numpy()
        missing = np.isnan(means)
        fallback = training_mean if np.isfinite(training_mean) else .5
        result.loc[targets.index,'municipal_history'] = np.where(missing,fallback,means)
        result.loc[targets.index,'history_missing'] = missing.astype(float)
        result.loc[targets.index,'training_mean'] = training_mean
    return result
