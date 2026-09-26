import numpy as np


def recommend(forecast, residuals, food_cost, contribution_margin):
    if not np.isfinite([food_cost, contribution_margin]).all() or food_cost <= 0 or contribution_margin <= 0:
        raise ValueError('Costs and contribution margin must be finite and positive.')
    if len(residuals) == 0:
        raise ValueError('Need earlier out-of-sample residuals before optimisation.')
    fractile = contribution_margin / (food_cost + contribution_margin)
    return max(0.0, float(forecast + np.quantile(residuals, fractile)))
