# YLD

Invite-only restaurant prep planner built with Vite, React and FastAPI. Each new workspace starts empty. An owner imports its service history from CSV, reviews per-dish costs, and then receives prep recommendations. Accounts and service data are isolated by workspace; one-use email links provide access.

## Local setup

```bash
npm install
python3 -m venv .venv
.venv/bin/pip install -r api/requirements.txt
cp .env.example .env
```

Edit `.env`, then load it into each shell that runs a YLD command:

```bash
set -a
source .env
set +a
```

Start the API:

```bash
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8817
```

In another shell, start Vite:

```bash
npm run dev -- --host 127.0.0.1
```

Vite proxies `/api` to FastAPI. `YLD_PUBLIC_URL` must match the browser origin Vite prints (normally `http://127.0.0.1:5173`).

## Invite a kitchen

For local development, generate a one-use link without sending email:

```bash
.venv/bin/python -m api.invite --email you@example.com --workspace 'Your Kitchen' --local-link
```

Open the printed link in the browser. Invitations expire in 48 hours and can be used once. After sign-in, sessions last seven days. Existing users can request a 15-minute sign-in link from `/login`.

For a private public-site preview before email delivery is configured, set `YLD_ENV=preview` and the exact HTTPS `YLD_PUBLIC_URL`, then use `--print-link` from a trusted server shell. Share the printed one-use URL privately; anyone holding it can enter that kitchen until it is redeemed. This option is disabled when `YLD_ENV=production` and is never exposed as a web endpoint.

For real email, set `RESEND_API_KEY`, `YLD_EMAIL_FROM` and the public `YLD_PUBLIC_URL`, then omit `--local-link`:

```bash
.venv/bin/python -m api.invite --email chef@example.com --workspace 'Your Kitchen'
```

`YLD_EMAIL_FROM` must use a [verified Resend sending domain](https://resend.com/docs/dashboard/domains/introduction). The server uses [Resend's email API](https://resend.com/docs/api-reference/emails/send-email) for transactional invitations. No key is sent to the browser. To add another person to an existing kitchen, use `--workspace-id ID` instead of `--workspace`.

## Import service history

The import screen offers a [blank CSV template](templates/service-history.csv). It contains column headings only, with no invented sales. Add one row for each dish at each service:

| Column | Meaning |
| --- | --- |
| `date` | Service date in `YYYY-MM-DD` format |
| `dish` | Dish name |
| `sold` | Whole number of portions sold |
| `covers` | Total covers that service; repeat for every dish on the same date |
| `prepared` | Optional whole number of portions prepared; enables actual leftover and waste comparisons |
| `ingredient_cost` | Optional per-portion ingredient cost in NZD |
| `price` | Optional per-portion sale price in NZD |
| `category` | Optional menu category |

The minimum required columns are `date,dish,sold,covers`. The import screen asks for per-dish costs if they are absent from the file. The owner previews and confirms an upload. A later import replaces the workspace’s current dishes and service history; download **Current data** before replacing it. No dishes or sales are added automatically.

Forecasts use up to 56 earlier services in a weighted ridge regression. Covers become automatic after 14 recorded service days. With fewer days, enter a cover estimate. History tests up to the last 28 records per dish, but only after that dish has 14 earlier sales records. Its service-date count reflects dates actually tested. Waste comparisons require prepared counts; sales alone cannot establish actual waste.

## Deploying for invited kitchens

Run `npm run build`, then serve the built site and `/api` from the same FastAPI server. A multi-stage `Dockerfile` is included. Configure HTTPS in front of FastAPI and set `YLD_PUBLIC_URL` to that exact HTTPS origin. Set `DATABASE_URL` to the restricted Postgres connection string for the private `yld` schema; apply the checked-in Supabase migrations first. Set `YLD_ENV=production` for fail-fast checks of these settings and the Resend credentials. Local development can omit `DATABASE_URL` and use SQLite at `YLD_DB_PATH`. Keep `.env` and database credentials out of source control.

Before inviting businesses, publish the seller's identity, address and contact email in the legal pages; confirm the hosting and Resend privacy disclosures; and test the live invite, sign-in, import, plan and sign-out flow. This site does not take payment or create subscriptions. See [LEGAL_LAUNCH_CHECKLIST.md](LEGAL_LAUNCH_CHECKLIST.md).

## Verification

```bash
npm run build
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```
