# Restaurant inventory AI — VS Code starter

The separate [cover prediction baseline](COVER_BASELINE.md) studies next-service covers from public data and does not feed this inventory modeller.

A runnable restaurant-level MVP: forecast food sold, optimise preparation with a newsvendor quantile, replay history, and report estimated net savings. A Streamlit dashboard lets you inspect one restaurant or upload a compatible CSV.

## Open and run on Windows

1. Open this folder in VS Code using **File → Open Folder**, or open `restaurant-inventory-ai.code-workspace`.
2. Install Python 3.12 or 3.13, [uv](https://docs.astral.sh/uv/getting-started/installation/), and the Microsoft **Python** extension if it is not already installed.
3. Open **Terminal → New Terminal** and run these commands from this project folder:

```powershell
uv sync --locked
uv run --locked python -m scripts.run_backtest --restaurant 10
uv run --locked streamlit run app.py
```

uv manages the `.venv` environment without PowerShell activation. This project was checked with Python 3.13.

4. Choose **Python: Select Interpreter** in VS Code's command palette and select `.venv`.
5. Open the local address printed by Streamlit. Use **Run historical analysis** in the dashboard. Stop the server with Ctrl+C.

The original GitHub CSV is included. To fetch it again:

```powershell
uv run --locked python -m scripts.download_data
```

## Commands

```powershell
# Single restaurant, explicit financial assumptions
uv run --locked python -m scripts.run_backtest --restaurant 10 --food-cost 8.5 --margin 14

# All restaurants, shared model with restaurant identity (takes longer)
uv run --locked python -m scripts.run_backtest --output outputs/all_restaurants

# Tests, including a real dashboard run
uv run --locked python -m pytest -q

# Optional full-history model export; not a historical evaluation model
uv run --locked python -m scripts.train
```

`--margin` means contribution margin per kilogram, not sale price. All monetary figures use the same assumed currency; the dashboard's currency label performs no conversion.

## Files and workflow

| File | Purpose |
|---|---|
| `src/load_data.py` | Validate quantities and restaurant/date keys, report gaps and categories |
| `src/features.py` | Grouped, shifted historical sales and calendar features |
| `src/demand_model.py` | Random Forest demand model |
| `src/optimizer.py` | Cost-sensitive quantile preparation recommendation |
| `src/backtest.py` | Chronological predictions and past-only residual calibration |
| `src/savings.py` | Shortage penalties, net savings and forecast metrics |
| `app.py` | Dashboard and CSV download |

The first 60% of unique dates start training. The next 20% generate out-of-sample residuals. Only the final 20% contributes to reported savings and accuracy. The model refits every seven observed dates, always using earlier dates only. Each prediction uses history available before that date. Earlier test outcomes can update later predictions, as in an operating one-period-ahead system; this is not a multi-day forecast made at one fixed origin.

Both Random Forest and the previous-seven-observation mean get their own uncertainty adjustment and stockout penalty. Compare both before claiming ML adds value. There is no automatic winner selection using the test set. If you tune the model after seeing these results, obtain a new untouched evaluation period.

Residuals are actual minus forecast. Calibration uses a restaurant's earlier residuals once at least 20 exist; otherwise it pools earlier residuals across restaurants. The 10th/90th residual quantiles give an empirical 80% interval. These intervals have no guaranteed coverage; the report measures coverage. Prep uses the residual quantile at `margin / (margin + food_cost)`.

## Reports

The command writes:

- `outputs/backtest_results.csv`: every scored recommendation, actual quantities, uncertainty, financial outcomes and timing audit fields.
- `outputs/savings_summary.csv`: metrics for each restaurant and policy.
- `outputs/data_audit.json`: full input file inspection.
- `outputs/run_metadata.json`: split dates, excluded cold starts and assumptions.

Net savings = (actual waste − simulated waste) × ingredient cost − simulated shortage × contribution margin. Negative outcomes are preserved. Annualised savings appear only where the scored dates form a complete daily series. Even then they are a simple daily-rate extrapolation, not an annual forecast.

## Data inspection and limitations

Source: https://github.com/mehedinaeem/restaurant-food-management-ml

Included file: `data/processed/restaurant_food_waste_final_dataset.csv` from that repository, downloaded on 2026-09-25/26. The included copy has 77,980 rows, 77 restaurants and 1,015 distinct dates, covering 2018-01-01 through 2020-10-11. There are no missing values or duplicate restaurant/date keys. Within-restaurant gaps are one day except for one 176-day gap. Prepared minus sold equals recorded waste to floating-point precision.

The original CSV already includes readable center types, categories and cuisines, but has no venue-name column. The source describes `restaurant_id` as a unique identifier, so there is no reliable way to discover real business names for these rows. The dashboard labels them with available details such as `TYPE_A · City 590 · Thai (ID 10)`. Those details help distinguish entries but are not venue names. The encoded EDA file is not needed, and no category meanings are guessed. For your own CSV, add an optional `restaurant_name` column with one consistent real name per restaurant ID to select by venue name. The upstream project discusses constructed proxy targets; its data should be treated as demonstration data rather than evidence of independently measured operational savings. Preserve upstream attribution and review its licence before redistribution or commercial use.

For uploads, required columns are `date`, `restaurant_id`, `food_sold_kg`, `food_prepared_kg` and `food_waste_kg`. `restaurant_name` is optional.

Important modelling boundaries:

- Sales are a demand proxy. Historical stockouts hide unmet demand. The simulator cannot recover that missing demand, and its savings are scenario estimates rather than causal or realised savings.
- Lag values mean prior observations, not necessarily prior calendar days. No missing day is silently converted into zero sales. `days_since_last_record` exposes gaps.
- Only restaurant identity, calendar fields and lagged sales enter the first model. Weather would need archived forecasts available before prep; promotions and events need known-in-advance records. Current-day customers, orders, prices, prepared quantities and waste are excluded.
- Past prep/waste features are deliberately omitted because changing the preparation policy changes these variables. This MVP replays observed sales; a deployed policy also changes future observed sales when it stocks out.
- Cold-start restaurant rows without previous sales are excluded and counted in metadata. The dashboard trains on the selected restaurant; the all-restaurant command fits a pooled model with restaurant identity. Their results can differ.
- Simulated waste assumes unsold preparation is wasted in that period. Shelf life, carryover, batch sizes, capacity, substitution and supplier lead times are not modelled.
- Recorded waste is used as the factual cost baseline. A balance-mismatch count is reported for uploaded data; investigate mismatches before interpreting savings.

## Next development step

Replace the aggregate data with `restaurant_id × item_id × service_date` records, using actual per-item ingredient costs, contribution margins, preparation, sales, waste and stockout flags. Group lag features and calibration by restaurant/item. Add service-time availability, shelf life and capacity constraints before using recommendations for live ordering.
