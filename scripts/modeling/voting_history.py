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


HISTORY_FEATURES = tuple(f"{prefix}_{suffix}" for prefix in
    ("history", "history_5y", "history_same_domain")
    for suffix in ("yes_mean", "vote_count", "missing"))


def build_v1_history_features(target_rows, history_source, config, domain_records=None):
    """Compute config-bound V1 summaries; unknown evidence is never an empty set.

    Unassigned source rows contribute only before the first training date (and
    from 2010). Empty partition declarations are preparation diagnostics only.
    Domain releases are selected independently at each target forecast cutoff.
    """
    source = history_source.copy()
    targets = target_rows.copy()
    for flag in ('is_special_unit','is_subsidiary','is_provisional'):
        if flag in source:
            source = source.loc[source[flag].eq(False)]
    for flag in [name for name in source if name.startswith('flag_')]:
        source = source.loc[source[flag].eq(False)]
    if 'preparation_status' in source:
        source = source.loc[source.preparation_status.eq('ready_for_enrichment')]
    for frame in (source, targets):
        for name in ('voting_date', 'forecast_at', 'result_available_at'):
            if name in frame:
                frame[name] = pd.to_datetime(frame[name], errors='coerce', utc=True, format='mixed')
        for name in ('municipality_id','geography_id','vote_id'):
            frame[name] = frame[name].astype('string')
    if 'target_share' not in source:
        source['target_share'] = source.yes_count / (source.yes_count + source.no_count)
    mapping = {pd.to_datetime(date, utc=True).normalize(): part for part, dates in
               zip(('train','validation','test'), (config.train_dates,config.validation_dates,config.test_dates)) for date in dates}
    first = min(mapping) if mapping else None
    source['partition'] = source.voting_date.dt.normalize().map(mapping).astype(object)
    source.loc[source.partition.isna() & source.voting_date.lt(first if first is not None else pd.Timestamp('2010-01-01',tz='UTC')), 'partition'] = 'context'
    source = source.loc[source.voting_date.isna() | source.voting_date.ge(pd.Timestamp('2010-01-01',tz='UTC'))]
    domains = None if domain_records is None else domain_records.copy()
    if domains is not None:
        domains['vote_id'] = domains.vote_id.astype(str)
        for name in ('published_at','reference_date'):
            domains[name] = pd.to_datetime(domains[name], errors='coerce', utc=True, format='mixed')
    domain_cache = {}
    def domain(vote, cutoff):
        key = (str(vote), cutoff)
        if key in domain_cache:
            return domain_cache[key]
        value = None
        if domains is not None:
            releases = domains.loc[domains.vote_id.eq(str(vote)) & domains.published_at.le(cutoff) & domains.reference_date.le(cutoff)]
            releases = releases.loc[releases.availability_status.eq('verified') & releases.domain_status.eq('known') & releases.object_match_status.eq('validated')]
            for field in ('availability_evidence','object_match_evidence','source_version'):
                releases = releases.loc[releases[field].notna() & releases[field].astype(str).str.strip().ne('')]
            if not releases.empty:
                latest = releases.loc[releases.published_at.eq(releases.published_at.max())]
                values = {tuple(sorted(set(x))) for x in latest.domain_codes}
                if len(values) == 1:
                    value = set(next(iter(values)))
        domain_cache[key] = value
        return value
    groups = {key: group for key, group in source.groupby(['municipality_id','geography_id'],dropna=False,sort=False)}  # noqa: C416
    records = []
    for row in targets.itertuples():
        output = {}
        candidates = groups.get((row.municipality_id,row.geography_id), source.iloc[:0])
        reason = None
        if pd.isna(row.forecast_at) or pd.isna(row.voting_date):
            reason = 'unknown_target_dates'
        elif pd.isna(row.geography_id) or not str(row.geography_id).strip():
            reason = 'unknown_geography'
        elif first is None:
            reason = 'undeclared_history_policy'
        allowed = ['context','train']
        partition = mapping.get(row.voting_date.normalize()) if pd.notna(row.voting_date) else None
        if config.mode == 'final_test' and config.refit_train_validation:
            allowed.append('validation')
        if config.history_policy == 'rolling' and partition in ('validation','test'):
            allowed.append('validation')
        if config.history_policy == 'rolling' and partition == 'test':
            allowed.append('test')
        pool = candidates.loc[(candidates.partition.isin(allowed) | candidates.voting_date.isna()) & (candidates.voting_date.lt(row.voting_date) | candidates.voting_date.isna()) & candidates.vote_id.ne(row.vote_id)]
        for prefix in ('history','history_5y','history_same_domain'):
            subset = pool
            status = reason
            if prefix == 'history_5y' and pd.notna(row.forecast_at):
                subset = subset.loc[(subset.voting_date.ge(row.forecast_at-pd.DateOffset(years=5)) & subset.voting_date.lt(row.forecast_at)) | subset.voting_date.isna()]
            if status is None and subset.voting_date.isna().any():
                status = 'unknown_voting_date'
            # Known late releases cannot contribute; missing proof cannot prove absence.
            subset = subset.loc[subset.result_available_at.isna() | subset.result_available_at.le(row.forecast_at)]
            if status is None and subset.result_available_at.lt(subset.voting_date).any():
                status = 'invalid_result_publication'
            if status is None and 'result_availability_status' in subset and not subset.result_availability_status.eq('verified').all():
                status = 'unknown_result_publication'
            if status is None:
                for field in ('result_available_at','result_availability_evidence','source_version') + tuple(name for name in ('result_source','result_source_version') if name in subset):
                    if subset[field].isna().any() or subset[field].astype(str).str.strip().eq('').any():
                        status = 'unknown_result_publication'
                        break
            if prefix == 'history_same_domain' and status is None:
                target_domain = domain(row.vote_id,row.forecast_at)
                memberships = [domain(vote,row.forecast_at) for vote in subset.vote_id]
                if target_domain is None or any(value is None for value in memberships):
                    status = 'unknown_domain_metadata'
                else:
                    subset = subset.loc[[bool(target_domain & value) for value in memberships]]
            if status is None and (subset.vote_id.duplicated().any() or not (np.isfinite(subset.target_share) & subset.target_share.between(0,1)).all()):
                status = 'ambiguous_history_result'
            if status is None:
                count = len(subset)
                output.update({prefix+'_yes_mean': float(subset.target_share.mean()) if count else np.nan,
                               prefix+'_vote_count': count, prefix+'_missing': bool(count == 0),
                               prefix+'_status': 'known' if count else 'no_antecedents'})
            else:
                output.update({prefix+'_yes_mean': np.nan,prefix+'_vote_count':np.nan,
                               prefix+'_missing':np.nan,prefix+'_status':status})
        records.append(output)
    columns = [name for prefix in ('history','history_5y','history_same_domain') for name in (prefix+'_yes_mean',prefix+'_vote_count',prefix+'_missing',prefix+'_status')]
    return pd.DataFrame(records,index=targets.index,columns=columns)
