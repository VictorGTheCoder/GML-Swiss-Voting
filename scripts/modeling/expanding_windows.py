"""Shared date schedule and publication-eligible training pool for model windows."""
from __future__ import annotations

import pandas as pd


def window_dates(config, partition):
    """Return normalized dates for the declared validation or final test windows."""
    if partition == 'test':
        return [pd.to_datetime(list(config.test_dates), utc=True, format='mixed').normalize()]
    if config.validation_windows is None:
        return [pd.to_datetime(list(config.validation_dates), utc=True, format='mixed').normalize()]
    return [pd.to_datetime(list(window), utc=True, format='mixed').normalize()
            for window in config.validation_windows]


def select_training_rows(rows, config, partition, declared_windows, index,
                         first_forecast, eligible_vote_ids=None):
    """Select rows in the expanding fit pool published by the window cutoff.

    Text callers can restrict the eligible training objects while sharing the
    same date, partition, publication, and evidence rules as non-text models.
    """
    if partition == 'test':
        fit_partitions = ['train', 'validation'] if config.refit_train_validation else ['train']
        allowed_dates = set(rows.loc[rows.partition.isin(fit_partitions), 'voting_date'])
    else:
        prior_validation = [date for previous in declared_windows[:index] for date in previous]
        allowed_dates = set(rows.loc[
            rows.partition.eq('train') | rows.voting_date.isin(prior_validation), 'voting_date'])
    eligible = (rows.voting_date.isin(allowed_dates)
        & rows.result_available_at.le(first_forecast)
        & rows.result_availability_evidence.notna()
        & rows.result_availability_evidence.astype(str).str.strip().ne(''))
    if eligible_vote_ids is not None:
        eligible &= rows.vote_id.isin(eligible_vote_ids)
    return rows.loc[eligible]
