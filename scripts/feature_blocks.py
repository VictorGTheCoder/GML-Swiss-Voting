"""Prepared, explicitly allowlisted source blocks; no source collection is performed."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureBlock:
    block_id: str
    scope: str
    records: pd.DataFrame
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]
    definitions: dict[str, str]
    source_url: str
    source_version: str
    geography_mode: str = 'historically_existing'
    prerequisite_reason: str | None = None


def join_feature_blocks(rows, blocks, geography_mode, *, retain_unverified=False):
    """As-of joins preserve keys; optional retrospective values stay explicitly unverified."""
    joined = pd.DataFrame(index=rows.index)
    report, manifests, coverage = [], {}, {}
    identifiers = [block.block_id for block in blocks]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Feature block identifiers must be unique')
    if 'history' in identifiers:
        raise ValueError("Feature block identifier 'history' is reserved for the history-only model")
    for block in blocks:
        if block.geography_mode not in ['historically_existing','retrospective_fixed']:
            raise ValueError('Feature block geography_mode must be declared')
        if block.scope not in ['municipality','object']:
            raise ValueError('Feature block scope must be municipality or object')
        if not block.block_id or '__' in block.block_id or not block.source_url or not block.source_version:
            raise ValueError('Feature block needs identifiers and source provenance')
        names = list(block.numeric_features) + list(block.categorical_features)
        if not names or len(names) != len(set(names)) or any(name not in block.definitions or not block.definitions[name] for name in names):
            raise ValueError('Feature allowlists must be unique, nonempty, and documented')
        outcomes = {'yes_count','no_count','votes_yes','votes_no','target_share','yes_share',
                    'turnout','ballot_total','eligible_voters','prediction','municipality_id','vote_id',
                    'ballots_cast','valid_ballots','blank_invalid_ballots','yes_pct_ofs','turnout_pct_ofs'}
        evaluation_only = {'evaluation_weight', 'evaluation_weights', 'eval_weight',
                           'electorate_weight', 'sample_weight', 'scoring_weight',
                           'metric_weight', 'row_weight'}
        if any(name.lower() in outcomes or name.lower() in evaluation_only or
               name.lower().startswith(('evaluation_weight_', 'eval_weight_')) for name in names):
            raise ValueError('Same-object outcome/key or evaluation-only fields cannot be predictors')
        for name in names:
            joined[f'{block.block_id}__{name}'] = np.nan if name in block.numeric_features else None
        provenance_columns = {
            f'{block.block_id}__availability_status': None,
            f'{block.block_id}__published_at': None,
            f'{block.block_id}__reference_date': None,
            f'{block.block_id}__availability_evidence': None,
            f'{block.block_id}__source_version': None,
        }
        if retain_unverified:
            for column, value in provenance_columns.items():
                if column in joined:
                    raise ValueError(f'Feature provenance column collides: {column}')
                joined[column] = value
        if block.prerequisite_reason is not None:
            if not block.prerequisite_reason.strip() or not block.records.empty:
                raise ValueError('Skipped blocks require a prerequisite reason and no records')
            coverage[block.block_id] = {'matched_rows': 0, 'eligible_rows': len(rows),
                'missing_values': {name: len(rows) for name in names}, 'skipped_rows': len(rows),
                'prerequisite_status': 'skipped', 'prerequisite_reason': block.prerequisite_reason}
            manifests[block.block_id] = {'scope': block.scope, 'source_url': block.source_url,
                'source_version': block.source_version, 'geography_mode': block.geography_mode,
                'numeric_features': list(block.numeric_features), 'categorical_features': list(block.categorical_features),
                'definitions': block.definitions}
            for _, row in rows.iterrows():
                report.append({'municipality_id': row.municipality_id, 'vote_id': row.vote_id,
                               'block_id': block.block_id, 'status': 'skipped'})
            if retain_unverified:
                joined.loc[:, f'{block.block_id}__availability_status'] = 'skipped'
            continue
        entity = 'municipality_id' if block.scope == 'municipality' else 'vote_id'
        required = [entity,'reference_date','published_at','availability_status','availability_evidence','source_version'] + names
        if block.scope == 'municipality':
            required += ['geography_id']
        missing = set(required) - set(block.records)
        if missing:
            raise ValueError(f'Missing prepared feature columns: {sorted(missing)}')
        source = block.records.copy().reset_index(drop=True)
        if block.scope == 'object':
            if {'object_match_status','object_match_evidence'} - set(source):
                raise ValueError('Object metadata requires validated correspondence columns')
        if source[entity].isna().any() or source[entity].astype(str).str.strip().eq('').any():
            raise ValueError('Feature records need entity identifiers')
        if source.source_version.isna().any() or source.source_version.ne(block.source_version).any():
            raise ValueError('Feature record source versions must match block provenance')
        source['published_at'] = pd.to_datetime(source.published_at, errors='coerce', utc=True, format='mixed')
        source['reference_date'] = pd.to_datetime(source.reference_date, errors='coerce', utc=True, format='mixed')
        source[entity] = source[entity].astype(str)
        if block.scope == 'municipality':
            # Match the evaluator's string reference IDs for CSV, Parquet and in-memory blocks.
            source['geography_id'] = source.geography_id.astype('string')
        duplicate_keys = [entity,'reference_date','published_at'] + (['geography_id'] if block.scope == 'municipality' else [])
        if source.duplicated(duplicate_keys,keep=False).any():
            raise ValueError('Feature release keys contain duplicate records')
        for name in block.numeric_features:
            source[name] = pd.to_numeric(source[name],errors='coerce')
            source.loc[~np.isfinite(source[name]),name] = np.nan
        for name in block.categorical_features:
            source[name] = source[name].map(lambda value: np.nan if pd.isna(value) else str(value))
        verified = (source.published_at.notna() & source.reference_date.notna()
                              & source.availability_status.eq('verified') & source.availability_evidence.notna()
                              & source.availability_evidence.astype('string').str.strip().ne('').fillna(False))
        if block.scope == 'object':
            verified &= (source.object_match_status.eq('validated') & source.object_match_evidence.notna()
                                   & source.object_match_evidence.astype('string').str.strip().ne('').fillna(False))
        source = source.sort_values(['published_at','reference_date'])
        all_releases = {key:group for key,group in source.groupby(entity,sort=False)}
        releases = {key:group.loc[verified.loc[group.index]] for key,group in all_releases.items()}
        counts = {'matched_rows': 0}
        context_columns = [entity,'forecast_at'] + (['geography_id'] if block.scope == 'municipality' else [])
        for context,targets in rows.groupby(context_columns,sort=False):
            entity_id,cutoff = context[:2]
            candidates = all_releases.get(entity_id)
            selected_publication, selected_reference, selected_evidence = None, None, None
            selected_version = None
            status = 'missing_entity'
            if candidates is not None:
                verified_candidates = releases.get(entity_id, candidates.iloc[:0])
                if pd.isna(cutoff):
                    timely = verified_candidates.iloc[:0]
                else:
                    timely = verified_candidates.loc[
                        verified_candidates.published_at.le(cutoff)
                        & verified_candidates.reference_date.le(cutoff)
                    ]
                status = 'unknown_availability' if verified_candidates.empty else 'unavailable_at_forecast'
                if not timely.empty:
                    if block.scope == 'municipality':
                        timely = timely.loc[timely.geography_id.eq(context[2])] if block.geography_mode == geography_mode else timely.iloc[:0]
                    status = 'incompatible_geography' if timely.empty else 'matched'
                    if not timely.empty:
                        selected = timely.iloc[-1]
                        for name in names:
                            joined.loc[targets.index,f'{block.block_id}__{name}'] = selected[name]
                        selected_publication,selected_reference,selected_evidence = str(selected.published_at),str(selected.reference_date),selected.availability_evidence
                        selected_version = selected.source_version
                        counts['matched_rows'] += len(targets)
                elif retain_unverified and status != 'incompatible_geography':
                    retrospective = candidates
                    if block.scope == 'municipality':
                        retrospective = retrospective.loc[retrospective.geography_id.eq(context[2])]
                    if not retrospective.empty:
                        selected = retrospective.sort_values(
                            ['reference_date','published_at','source_version'], na_position='last', kind='stable'
                        ).iloc[-1]
                        for name in names:
                            joined.loc[targets.index,f'{block.block_id}__{name}'] = selected[name]
                        selected_publication = None if pd.isna(selected.published_at) else str(selected.published_at)
                        selected_reference = None if pd.isna(selected.reference_date) else str(selected.reference_date)
                        selected_evidence = selected.availability_evidence
                        selected_version = selected.source_version
                if retain_unverified:
                    joined.loc[targets.index, f'{block.block_id}__availability_status'] = status
                    joined.loc[targets.index, f'{block.block_id}__published_at'] = selected_publication
                    joined.loc[targets.index, f'{block.block_id}__reference_date'] = selected_reference
                    joined.loc[targets.index, f'{block.block_id}__availability_evidence'] = selected_evidence
                    joined.loc[targets.index, f'{block.block_id}__source_version'] = selected_version
            counts[status+'_rows'] = counts.get(status+'_rows',0) + (len(targets) if status != 'matched' else 0)
            context_report = targets[['municipality_id','vote_id']].assign(block_id=block.block_id,status=status,
                published_at=selected_publication,reference_date=selected_reference,
                availability_evidence=selected_evidence,source_version=selected_version)
            report.extend(context_report.to_dict('records'))
        counts['missing_values'] = {name:int(joined[f'{block.block_id}__{name}'].isna().sum()) for name in names}
        counts['input_records'] = len(source)
        counts['eligible_rows'] = len(rows)
        counts['prerequisite_status'] = 'usable' if counts['matched_rows'] else 'no_admissible_matches'
        coverage[block.block_id] = counts
        manifests[block.block_id] = {'scope': block.scope, 'source_url': block.source_url,
            'source_version': block.source_version, 'geography_mode': block.geography_mode,
            'numeric_features': list(block.numeric_features), 'categorical_features': list(block.categorical_features),
            'definitions': block.definitions,
            'object_correspondence': 'validated object_match_status and nonempty object_match_evidence required' if block.scope == 'object' else None,
            'records_sha256': hashlib.sha256(block.records.to_json(orient='split',date_format='iso').encode()).hexdigest()}
    return joined, pd.DataFrame(report), manifests, coverage


def prepare_statpop_nationality(prepared: pd.DataFrame, *, source_version: str,
                               geography_id: str | None, source_url: str,
                               geography_mode: str = 'historically_existing',
                               publication_evidence: pd.DataFrame | None = None) -> FeatureBlock:
    """Adapt teammates' year/code/population/foreign table; never infer historical releases."""
    required = {'year','code','population','foreign'}
    if required - set(prepared):
        raise ValueError(f'Missing prepared STATPOP columns: {sorted(required-set(prepared))}')
    source = prepared.copy()
    if source[['year','code']].isna().any().any():
        raise ValueError('Prepared STATPOP needs year and municipality identifiers')
    source['code'] = source.code.astype(str)
    if source.duplicated(['year','code']).any():
        raise ValueError('Prepared STATPOP contains duplicate municipality/year keys')
    source['reference_date'] = pd.to_datetime(source.year.astype(str) + '-12-31', errors='raise',utc=True)
    population = pd.to_numeric(source.population,errors='coerce')
    foreign = pd.to_numeric(source.foreign,errors='coerce')
    valid = np.isfinite(population) & population.gt(0) & np.isfinite(foreign) & foreign.ge(0) & foreign.le(population)
    source['population'] = population.where(valid)
    source['foreign_share'] = (foreign/population).where(valid)
    source['published_at'] = None
    source['availability_evidence'] = None
    source['availability_status'] = 'unknown'
    if publication_evidence is not None:
        evidence = publication_evidence.copy()
        required_evidence = {'year','code','published_at','availability_evidence','source_version'}
        if required_evidence - set(evidence):
            raise ValueError(f'Missing STATPOP evidence columns: {sorted(required_evidence-set(evidence))}')
        evidence['code'] = evidence.code.astype(str)
        if evidence.duplicated(['year','code']).any():
            raise ValueError('STATPOP publication evidence has duplicate keys')
        if evidence.source_version.isna().any() or evidence.source_version.ne(source_version).any():
            raise ValueError('STATPOP evidence must identify the exact prepared source version')
        source = source.drop(columns=['published_at','availability_evidence']).merge(
            evidence[['year','code','published_at','availability_evidence']],on=['year','code'],how='left',validate='one_to_one')
        verified = source.published_at.notna() & source.availability_evidence.notna() & source.availability_evidence.astype(str).str.strip().ne('')
        source.loc[verified,'availability_status'] = 'verified'
    source['municipality_id'] = source.code
    source['source_version'] = source_version
    source['geography_id'] = geography_id
    return FeatureBlock('statpop_nationality','municipality',source,
                        ('population','foreign_share'),(),
                        {'population':'Permanent resident population, persons',
                         'foreign_share':'Foreign permanent resident population / total permanent resident population, share'},
                        source_url,source_version,geography_mode)


def load_feature_blocks(manifest_path):
    """Load JSON block descriptors and prepared CSVs; paths resolve beside the manifest."""
    import json
    from pathlib import Path
    path = Path(manifest_path)
    descriptors = json.loads(path.read_text())
    if not isinstance(descriptors,list):
        raise ValueError('Feature block manifest must contain a JSON list')
    blocks = []
    for descriptor in descriptors:
        parameters = descriptor.copy()
        records_path = parameters.pop('records_path', None)
        parameters['records'] = pd.read_csv(path.parent / records_path,dtype={'municipality_id':str,'vote_id':str,'geography_id':str}) if records_path else pd.DataFrame()
        blocks.append(FeatureBlock(**parameters))
    return tuple(blocks)


def synthetic_feature_example():
    """Illustrative fixture only; evidence does not describe Swiss source publications."""
    source = pd.DataFrame({'year':[2018]*3,'code':['a','b','c'],'population':[100,200,300],
                           'foreign':[20,40,60]})
    evidence = pd.DataFrame({'year':[2018]*3,'code':['a','b','c'],'published_at':['2019-01-01']*3,
                             'availability_evidence':['synthetic-release']*3,'source_version':['synthetic-statpop-v1']*3})
    return prepare_statpop_nationality(source,source_version='synthetic-statpop-v1',
        geography_id='synthetic-g1',source_url='https://example.test/synthetic-statpop',publication_evidence=evidence)
