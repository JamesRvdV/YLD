# Generalisation probe for meal demand

The earlier seven-dish baseline was evaluated on later dates from the same restaurant. That does not measure transfer to another venue. This probe trains one pooled model on many meal series and holds entire centres and entire meals out of fitting. It is an **offline research result**, not YLD's active forecast or a claim of waste savings.

## Public data and reproduction

The [Genpact Food Demand Forecasting challenge](https://datahack.analyticsvidhya.com/contest/genpact-machine-learning-hackathon-1/) has weekly orders by fulfilment centre and meal. A [public copy of `train.csv`](https://github.com/Shivansh-Commits/Food-Demand-Forecasting-DATA-SCIENCE-CHALLANGE/blob/main/train.csv) has 456,548 rows, 77 centres, 51 meals, and 145 weeks. The evaluated file's SHA-256 is `a2ed2d7c6905d63a9361d8dd35bc06c8a597831f7185644e0f33ad7bfe20cc81`. The source CSV is not included here; check the source terms before redistributing it.

From the `ml` directory after `uv sync --locked`:

```sh
uv run --locked python global_meal_model.py /path/to/train.csv
```

This writes `global_meal_report.json` and a locally regenerated `global_meal_model.joblib` (ignored by Git). The script uses only prior orders in the same centre/meal series, plus the number of weeks since the last observation. It needs at least 12 previous observations. It does not use centre or meal IDs, target-week price or promotions, or current-week orders as predictors.

To forecast one new centre/meal series after training, give its observed history as a CSV with `week,center_id,meal_id,num_orders` and one row per observed week:

```sh
uv run --locked python global_meal_model.py /path/to/one_series_history.csv --forecast-week 146
```

The week must follow the last observed week. The numeric IDs identify the output series but are not model features. The command returns an expected order count and the recent-four-observation baseline for comparison.

The split is fixed by seed 42. Training uses weeks up to 116, then weeks 117–129 at familiar centres and meals select between two fixed Poisson gradient boosting settings. The selected model is refit using familiar series through week 129. Weeks 130–145 are the untouched test period; separate cohorts hold out 15 centres, 10 meals, or both. Within held-out series, earlier actual orders are available to form lag features, as they would be for a new kitchen with its own sales history. This is **transfer with local history**, not a cold-start test with no observations.

| Test cohort | Meal-weeks | Model MAE | Recent 4 MAE | Last week MAE | Series where model beats recent 4 |
|---|---:|---:|---:|---:|---:|
| Seen centres and meals | 34,289 | 85.41 | 96.94 | 98.89 | 58.6% |
| Unseen centres | 8,172 | 77.28 | 87.68 | 89.42 | 58.2% |
| Unseen meals | 8,113 | 109.69 | 125.17 | 114.13 | 66.2% |
| Both unseen | 1,902 | 94.02 | 107.41 | 102.23 | 64.6% |

MAE is orders per meal per week. The report also includes 12-observation and four-week-lag baselines, WAPE, cohort counts, and exact held-out IDs. The model beats each listed simple baseline on aggregate in all four cohorts. It does not win for every series.

## Meaning for YLD

This is evidence that one pooled model can transfer to unfamiliar centres and meals **within this weekly delivery dataset**, given roughly three months of local history. It does not establish transfer to daily restaurant dishes, low-volume or newly launched dishes, or a venue with no history. Missing centre/meal/weeks are not converted into zero orders; only observed rows are evaluated, so the test does not cover menu availability decisions. Recorded orders can also miss unmet demand if supply is constrained.

Before using a pooled model in YLD, collect dish-by-service sales, preparation, leftovers, stockouts, prices and known-in-advance events from multiple venues. Hold whole venues and dishes out of training, then compare forecast error and realised preparation outcomes with a simple recent-sales rule. Route a dish to the simple rule when the pooled model has not earned an advantage on its own history. The existing production API accepts a fixed JSON ridge model, so this Python artifact is intentionally separate from live forecasts.
