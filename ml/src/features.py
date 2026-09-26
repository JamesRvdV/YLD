import pandas as pd


def make_features(df):
    """All lags are observation periods, not assumed calendar days.

    transform keeps rolling windows inside each restaurant. shift precedes rolling.
    Sales-only histories avoid feeding factual prep/waste into a changed prep policy.
    """
    out = df.sort_values(['restaurant_id', 'date']).reset_index(drop=True).copy()
    grouped = out.groupby('restaurant_id', sort=False)['food_sold_kg']
    numeric = []
    for lag in (1, 2, 7, 14):
        name = f'sales_lag_{lag}'
        out[name] = grouped.shift(lag)
        numeric.append(name)
    for window in (7, 14, 28):
        name = f'sales_rolling_{window}'
        out[name] = grouped.transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean())
        numeric.append(name)
    out['days_since_last_record'] = out.groupby('restaurant_id').date.diff().dt.days
    out['day_of_week'] = out.date.dt.dayofweek
    out['month'] = out.date.dt.month
    out['week_of_year'] = out.date.dt.isocalendar().week.astype(int)
    out['year'] = out.date.dt.year
    numeric += ['days_since_last_record', 'day_of_week', 'month', 'week_of_year', 'year']
    return out, numeric, ['restaurant_id']
