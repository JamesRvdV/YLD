import argparse
import json
from pathlib import Path

from src.backtest import run_backtest
from src.load_data import load_data


def main():
    parser = argparse.ArgumentParser(description='Forecast demand and backtest prep policies.')
    parser.add_argument('--data', default='data/raw/restaurant_data.csv')
    parser.add_argument('--output', default='outputs')
    parser.add_argument('--food-cost', type=float, default=8.5)
    parser.add_argument('--margin', type=float, default=14)
    parser.add_argument('--retrain-every', type=int, default=7)
    parser.add_argument('--restaurant', help='Optional single restaurant ID')
    args = parser.parse_args()
    df, audit = load_data(args.data)
    if args.restaurant:
        df = df[df.restaurant_id == args.restaurant]
        if df.empty:
            parser.error('Restaurant ID not found.')
    results, summary, metadata = run_backtest(df, args.food_cost, args.margin, args.retrain_every)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    results.to_csv(output / 'backtest_results.csv', index=False)
    summary.to_csv(output / 'savings_summary.csv', index=False)
    (output / 'data_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    (output / 'run_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print('Scenario estimates only; food cost and margin are user assumptions.')
    print(summary.groupby('policy')[['net_savings', 'potential_lost_margin']].sum().to_string())
    print(f'Reports saved in {output.resolve()}')


if __name__ == '__main__':
    main()
