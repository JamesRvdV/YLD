import numpy as np
import pandas as pd
import pytest

from src.features import make_features
from src.load_data import load_data
from src.optimizer import recommend
from src.savings import simulate
from src.backtest import run_backtest


def fixture_data():
    return pd.DataFrame([
        {'date': day, 'restaurant_id': restaurant, 'food_sold_kg': float(20 + i % 7 + offset),
         'food_prepared_kg': float(30 + i % 7 + offset), 'food_waste_kg': 10.0}
        for restaurant, offset in [('A', 0), ('B', 1000)]
        for i, day in enumerate(pd.date_range('2024-01-01', periods=40))
    ])


def test_features_do_not_cross_restaurants_or_include_today():
    data = fixture_data()
    features, _, _ = make_features(data.sample(frac=1, random_state=1))
    b = features[features.restaurant_id == 'B']
    assert pd.isna(b.iloc[0].sales_rolling_7)
    assert b.iloc[1].sales_rolling_7 == 1020
    changed = data.copy()
    changed.loc[changed.date >= '2024-01-10', 'food_sold_kg'] = 99999
    other, _, _ = make_features(changed)
    columns = [c for c in features if c.startswith('sales_')]
    pd.testing.assert_frame_equal(features.loc[features.date <= '2024-01-10', columns],
                                  other.loc[other.date <= '2024-01-10', columns])


def test_financial_examples_and_negative_savings():
    data = pd.DataFrame({'recommended_prep_kg': [86, 75, 0], 'food_sold_kg': [80]*3,
                         'food_waste_kg': [20]*3})
    result = simulate(data, 8, 15)
    assert result.net_savings.tolist() == [112, 85, -1040]
    assert result.potential_lost_margin.iloc[1] == 75


def test_cost_sensitive_quantile():
    residuals = np.arange(-10, 11)
    assert recommend(50, residuals, 8, 20) > recommend(50, residuals, 8, 5)
    assert recommend(0, [-20, -10], 8, 5) == 0
    with pytest.raises(ValueError):
        recommend(50, [], 8, 15)


def test_loader_rejects_duplicates(tmp_path):
    data = fixture_data()
    path = tmp_path / 'data.csv'
    pd.concat([data, data.iloc[:1]]).to_csv(path, index=False)
    with pytest.raises(ValueError, match='duplicate'):
        load_data(path)


def test_backtest_is_causal_and_policies_are_comparable():
    data = fixture_data()
    rows, summary, _ = run_backtest(data, retrain_every=7)
    assert (rows.model_trained_through < rows.date).all()
    assert (rows.calibration_through < rows.date).all()
    assert set(rows.policy) == {'rolling_mean', 'random_forest'}
    assert len(summary) == 4
    assert rows.groupby('policy').size().nunique() == 1
    changed = data.copy()
    cutoff = pd.Timestamp('2024-02-07')
    changed.loc[changed.date >= cutoff, 'food_sold_kg'] += 500
    replay, _, _ = run_backtest(changed, retrain_every=7)
    columns = ['forecast_kg', 'recommended_prep_kg', 'lower_80_kg', 'upper_80_kg']
    pd.testing.assert_frame_equal(rows.loc[rows.date <= cutoff, columns],
                                  replay.loc[replay.date <= cutoff, columns])


def test_dashboard_loads_and_runs():
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    app = AppTest.from_file(Path('app.py').resolve(), default_timeout=90).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert len(app.metric) == 3
