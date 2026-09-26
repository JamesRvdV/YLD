from collections import defaultdict

import numpy as np
import pandas as pd

from src.demand_model import build_model
from src.features import make_features
from src.optimizer import recommend
from src.savings import simulate, summarize


def run_backtest(df, food_cost=8.5, margin=14.0, retrain_every=7):
    """Expanding date-group replay. First 60% train, next 20% calibrate, last 20% score.

    Every date is predicted before that date's outcomes enter residual calibration.
    Refitting is periodic; predictions and historical updates are one period ahead.
    """
    if retrain_every < 1:
        raise ValueError('retrain_every must be positive.')
    if not np.isfinite([food_cost, margin]).all() or min(food_cost, margin) <= 0:
        raise ValueError('Costs must be positive finite values.')
    data, numeric, categorical = make_features(df)
    dates = sorted(data.date.unique())
    if len(dates) < 30:
        raise ValueError('Need at least 30 distinct dates for train/calibration/test.')
    first, test = int(len(dates) * .6), int(len(dates) * .8)
    features = numeric + categorical
    pool = defaultdict(list)
    local = defaultdict(list)
    records = []
    model = None
    trained_through = None
    for step, day in enumerate(dates[first:]):
        train = data[(data.date < day) & data.sales_lag_1.notna()]
        current = data[(data.date == day) & data.sales_lag_1.notna()].copy()
        if train.empty:
            raise ValueError('Insufficient restaurant histories.')
        if model is None or step % retrain_every == 0:
            model = build_model(numeric, categorical)
            model.fit(train[features], train.food_sold_kg)
            trained_through = train.date.max()
        if current.empty:
            continue
        predictions = {
            'random_forest': np.maximum(0, model.predict(current[features])),
            'rolling_mean': current.sales_rolling_7.to_numpy(),
        }
        for policy, values in predictions.items():
            for (_, row), forecast in zip(current.iterrows(), values):
                key = (policy, row.restaurant_id)
                residuals = local[key] if len(local[key]) >= 20 else pool[policy]
                if day >= dates[test] and residuals:
                    record = {c: row[c] for c in ['date', 'restaurant_id', 'food_sold_kg', 'food_prepared_kg', 'food_waste_kg']}
                    record.update(policy=policy, forecast_kg=float(forecast),
                                  recommended_prep_kg=recommend(forecast, residuals, food_cost, margin),
                                  lower_80_kg=max(0, forecast + np.quantile(residuals, .1)),
                                  upper_80_kg=max(0, forecast + np.quantile(residuals, .9)),
                                  calibration_n=len(residuals),
                                  calibration_scope='restaurant' if len(local[key]) >= 20 else 'pooled',
                                  model_trained_through=trained_through,
                                  calibration_through=dates[first + step - 1])
                    records.append(record)
            # Update only after all restaurants on this date have predictions.
            for (_, row), forecast in zip(current.iterrows(), values):
                residual = float(row.food_sold_kg - forecast)
                pool[policy].append(residual)
                local[(policy, row.restaurant_id)].append(residual)
    if not records:
        raise ValueError('No eligible test rows. Check restaurant history lengths.')
    results = simulate(pd.DataFrame(records), food_cost, margin)
    summary = summarize(results, food_cost, margin)
    metadata = {'initial_training_end': str(pd.Timestamp(dates[first-1]).date()),
                'calibration_start': str(pd.Timestamp(dates[first]).date()),
                'test_start': str(pd.Timestamp(dates[test]).date()),
                'test_end': str(pd.Timestamp(dates[-1]).date()),
                'retrain_every_observed_dates': retrain_every,
                'critical_fractile': margin / (margin + food_cost),
                'excluded_cold_start_test_rows': int(((data.date >= dates[test]) & data.sales_lag_1.isna()).sum()),
                'interpretation': 'Scenario estimate using observed sales as demand; not proven realised savings.'}
    return results, summary, metadata
