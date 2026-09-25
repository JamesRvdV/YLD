# YLD

Local restaurant prep planner built with Vite, React, Tailwind CSS, and FastAPI.

## Run locally

```bash
npm install
python3 -m venv .venv
.venv/bin/pip install -r api/requirements.txt
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8817
```

In a second terminal:

```bash
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173. Vite proxies `/api` to FastAPI on port 8817.

## Simple product flow

1. Open the demo to see tomorrow's plan. After 14 recorded services, YLD estimates covers automatically; before that, enter an expected cover count. You can override the estimate for an unusual service.
2. Review a prep quantity for each dish, its likely demand range, ingredient cost, and expected leftovers.
3. After service, log prepared and sold portions. Leftovers are calculated and added to the sales history.
4. Use **Menu costs** to update ingredient cost and sale price per portion. The next plan uses those values.
5. Use **History** to compare the planner's recommendations with the kitchen's usual prep over 28 past services.

The demo starts with five sample dishes and 84 sample services, so there is a usable plan immediately. It is a local prototype, not a production account system.

## How the recommendation works

The local database starts with 84 seeded services for five dishes. After 14 distinct recorded service days, a weighted ridge model estimates tomorrow's covers from weekday patterns and recent trend. Each dish forecast then uses up to 56 earlier services and fits a weighted ridge regression on covers, weekend demand, and trend. Recent observations receive more weight. An 80% demand range comes from the model's residual variation.

For each dish, the optimizer checks possible prep quantities and minimizes expected ingredient waste plus the contribution margin and service penalty of missed sales. The planner uses a balanced default; covers can be manually overridden when needed. Service actuals are stored in a local SQLite database (`api/yld.db`) and used in subsequent forecasts.

The history page runs a 28-service walk-forward comparison: every recommendation is trained only on data available before that service. Historic sales can be capped by stockouts, so the displayed missed-sales count is a lower-bound comparison against recorded sales, not a measurement of unknown demand.

## Current scope

This is a local demo with fictional restaurant data. It does not connect to an existing Supabase project or deploy to Vercel; the Supabase account currently has unrelated projects, and this app has been kept local as requested.
