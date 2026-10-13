"""Shared percentage-point scoring for wider and paired municipal predictions."""
from __future__ import annotations

import numpy as np
import pandas as pd


def evaluation_weights(rows):
    weights = pd.to_numeric(rows.get('evaluation_weight',pd.Series(np.nan,index=rows.index)),errors='coerce')
    valid = np.isfinite(weights) & weights.gt(0)
    return weights,valid


def score_predictions(rows):
    errors = (rows.prediction-rows.target_share).abs()*100
    weights,valid = evaluation_weights(rows)
    return {'mae_pp':float(errors.mean()) if len(rows) else None,'rows':len(rows),
            'electorate_weighted_mae_pp':float(np.average(errors[valid],weights=weights[valid])) if valid.any() else None,
            'weighted_rows':int(valid.sum())}
