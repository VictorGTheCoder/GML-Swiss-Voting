"""Independent prepared-source comparisons on paired municipal observations."""
from __future__ import annotations


def ablation_reports(predictions, blocks, manifests, coverage, regularized, mode):
    reports = {}
    reference = predictions.loc[predictions.model.eq('ridge_history')]
    for block in blocks:
        model = f'ridge_{block.block_id}'
        candidate = predictions.loc[predictions.model.eq(model)]
        paired = reference.merge(candidate, on=['municipality_id','vote_id'], suffixes=('_reference','_candidate'), validate='one_to_one')
        report = {**manifests[block.block_id], 'model': model, 'reference_model': 'ridge_history',
                  'evaluation_partition': 'test' if mode == 'final_test' else 'validation',
                  'features': regularized.get(model, {}).get('features', []),
                  'missingness_and_join_losses': coverage[block.block_id],
                  'wider_nontext_coverage': {'rows': len(reference), 'objects': int(reference.vote_id.nunique()),
                                            'dates': int(reference.voting_date.nunique())},
                  'compared_row_keys': paired[['municipality_id','vote_id']].values.tolist(),
                  'paired_rows': len(paired),
                  'paired_objects': int(paired.vote_id.nunique()),
                  'paired_dates': int(paired.voting_date_reference.nunique()),
                  'status': 'completed' if len(paired) else 'skipped',
                  'prerequisite_reason': (block.prerequisite_reason or
                      ('No admissible source matches at forecast time' if coverage[block.block_id]['matched_rows'] == 0
                       else 'No paired admissible observations' if paired.empty else None)),
                  'paired_reference_mae_pp': None, 'paired_candidate_mae_pp': None, 'paired_mae_change_pp': None}
        if not paired.empty:
            reference_mae = float((paired.prediction_reference-paired.target_share_reference).abs().mean()*100)
            candidate_mae = float((paired.prediction_candidate-paired.target_share_reference).abs().mean()*100)
            report.update(paired_reference_mae_pp=reference_mae, paired_candidate_mae_pp=candidate_mae,
                          paired_mae_change_pp=candidate_mae-reference_mae)
        reports[block.block_id] = report
    return reports
