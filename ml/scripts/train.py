from pathlib import Path
import joblib
from src.load_data import load_data
from src.features import make_features
from src.demand_model import build_model

if __name__ == '__main__':
    data, _ = load_data('data/raw/restaurant_data.csv')
    frame, numeric, categorical = make_features(data)
    frame = frame[frame.sales_lag_1.notna()]
    model = build_model(numeric, categorical)
    model.fit(frame[numeric + categorical], frame.food_sold_kg)
    Path('outputs').mkdir(exist_ok=True)
    joblib.dump({'model': model, 'features': numeric + categorical,
                 'trained_through': str(frame.date.max()),
                 'note': 'Full-history fit, never use for historical evaluation.'}, 'outputs/demand_model.joblib')
    print('Saved full-history demand model. Use run_backtest for honest evaluation.')
