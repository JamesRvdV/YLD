import numpy as np
import pandas as pd


def simulate(rows, food_cost, contribution_margin):
    out = rows.copy()
    out['simulated_waste_kg'] = (out.recommended_prep_kg - out.food_sold_kg).clip(lower=0)
    out['potential_shortage_kg'] = (out.food_sold_kg - out.recommended_prep_kg).clip(lower=0)
    out['actual_waste_cost'] = out.food_waste_kg * food_cost
    out['simulated_waste_cost'] = out.simulated_waste_kg * food_cost
    out['waste_kg_avoided'] = out.food_waste_kg - out.simulated_waste_kg
    out['avoided_waste_cost'] = out.actual_waste_cost - out.simulated_waste_cost
    out['potential_lost_margin'] = out.potential_shortage_kg * contribution_margin
    out['net_savings'] = out.avoided_waste_cost - out.potential_lost_margin
    return out


def summarize(rows, food_cost, margin):
    summaries = []
    for (policy, restaurant), g in rows.groupby(['policy', 'restaurant_id']):
        actual = g.food_sold_kg.to_numpy()
        error = g.forecast_kg.to_numpy() - actual
        # Annualisation only for a verified complete daily evaluation series.
        span = (g.date.max() - g.date.min()).days + 1
        daily = g.date.nunique() == span and span > 1
        waste = g.food_waste_kg.sum()
        summaries.append({
            'policy': policy, 'restaurant_id': restaurant,
            'start': str(g.date.min().date()), 'end': str(g.date.max().date()),
            'observations': len(g), 'calendar_days': span,
            'food_cost_per_kg_assumption': food_cost, 'margin_per_kg_assumption': margin,
            **{c: float(g[c].sum()) for c in ['food_prepared_kg', 'food_sold_kg', 'food_waste_kg',
                'actual_waste_cost', 'simulated_waste_kg', 'simulated_waste_cost', 'waste_kg_avoided',
                'avoided_waste_cost', 'potential_shortage_kg', 'potential_lost_margin', 'net_savings']},
            'waste_reduction_pct': 100 * g.waste_kg_avoided.sum() / waste if waste else np.nan,
            'mae_kg': float(np.abs(error).mean()), 'rmse_kg': float(np.sqrt((error**2).mean())),
            'wape_pct': 100 * np.abs(error).sum() / actual.sum() if actual.sum() else np.nan,
            'interval_80_coverage': float(((actual >= g.lower_80_kg) & (actual <= g.upper_80_kg)).mean()),
            'annualised_net_savings': float(g.net_savings.sum() / span * 365) if daily else np.nan,
            'annualisation_note': 'Daily-rate extrapolation, not a forecast' if daily else 'Unavailable: daily coverage not established',
        })
    return pd.DataFrame(summaries)
