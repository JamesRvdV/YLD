# YLD

Invite-only restaurant prep planner built with Vite, React and FastAPI. Each new workspace starts empty. An owner imports its service history from CSV or XLSX, reviews per-dish costs, and then receives prep recommendations. Accounts and service data are isolated by workspace. Admin invitations set up a password for future sign-ins.

## Local setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Node.js 22, then run:

```bash
npm install
uv sync --locked
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
uv run --locked uvicorn api.main:app --reload --host 127.0.0.1 --port 8817
```

In another shell, start Vite:

```bash
npm run dev -- --host 127.0.0.1
```

Vite proxies `/api` to FastAPI. `YLD_PUBLIC_URL` must match the browser origin Vite prints (normally `http://127.0.0.1:5173`).

## Bootstrap the admin account

On the trusted server shell, create a one-use setup link for the only admin account:

```bash
uv run --locked python -m api.invite --email axel.mckenna7@gmail.com --workspace 'Admin Kitchen'
```

Open the printed link privately, set a password of at least 12 characters, then sign in at `/login`. This command prints a link only for the designated admin address; it sends no email. The printed link is a secret and works once for 48 hours. Sessions last seven days.

For a deployed site, set `YLD_PUBLIC_URL` to its exact HTTPS origin before running the command. Only the trusted server shell should see the setup link.

## Invite a kitchen

Sign in as `axel.mckenna7@gmail.com`, open **Admin** in the dashboard (or `/admin`), and send an invitation for a new kitchen or an existing one. Only this account can load the admin page or call the invitation API. Sending an invitation to an existing account lets that person reset their password and ends their existing sessions when the link is used. People with older link-only accounts need a new admin invitation before they can sign in with a password. The public login page does not send links.

Set `RESEND_API_KEY`, `YLD_EMAIL_FROM`, and `YLD_PUBLIC_URL` on the API server to deliver invitations. `YLD_EMAIL_FROM` must use a [verified Resend sending domain](https://resend.com/docs/dashboard/domains/introduction). The server uses [Resend's email API](https://resend.com/docs/api-reference/emails/send-email); no key is sent to the browser.

## Load menu costs and service history

The YLD Agent modal accepts two CSV or XLSX files, each up to 4 MB. The menu file needs an item name, per-portion ingredient cost, and sale price. Sales dish names must match menu item names (case is ignored); unmatched dishes stop the import before existing data is replaced. The [blank sales CSV template](templates/service-history.csv) contains column headings only. Add one row for each dish at each service:

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

The minimum required sales information is `date,dish,sold,covers`. The converter supports one-dish-per-row and dish-as-column layouts. Missing covers cannot be inferred from sales. The modal shows the service count and matched menu dishes before the owner confirms that the new files replace the current menu and service history. The current modal uses the proposed sheet, header, and column mapping automatically; it does not yet offer a manual mapping correction screen. Date values in the automatic path should be ISO dates or Excel date cells, and repeated transactions must already be aggregated by dish and date.

Header rules work without an external API. To enable optional agent suggestions for the sales file, configure a dedicated `YLD_IMPORT_AGENT_API_KEY` on the API server and optionally `YLD_IMPORT_AGENT_MODEL` (default `gpt-4o-mini`). The owner must select the agent mapping option in the modal. Only then are sheet names, headers, and up to three sample rows per sheet sent for a suggestion; the model's mapping is checked against actual headers before use. Menu mapping uses header rules. Conversion and row validation remain deterministic. Download **Current data** before replacing a workspace's history.

Forecasts use up to 56 earlier services in a weighted ridge regression. Covers become automatic after 14 recorded service days. With fewer days, enter a cover estimate. History tests up to the last 28 records per dish, but only after that dish has 14 earlier sales records. Its service-date count reflects dates actually tested. Waste comparisons require prepared counts; sales alone cannot establish actual waste.

The `templates/restaurant-demo-*.csv` files are synthetic demo inputs, not restaurant results. Their service history includes varied prepared quantities and leftovers to illustrate an over-preparation scenario. Importing them replaces the current workspace's menu and history. Any cost difference shown after import is a projection or historical simulation, not measured savings from a real kitchen; the replay also shows observed sales that a simulated plan would have put at risk.

An optional [Codex model worker](deploy/MODEL_PIPELINE.md) can train a kitchen-specific demand model once a dish has 56 services. An eligible modal import queues training automatically when that worker is enabled. The worker tests a candidate against the existing forecast on 14 held-out services before activating it. The dashboard polls the job stage every five seconds and shows a stage-based progress bar; it is not an estimated time or percentage. Local deployments leave the worker off by default; the production VM worker was enabled after an isolated live smoke test on 2026-09-26.

An offline [public-data cover prediction baseline](ml/COVER_BASELINE.md) includes a trained model, source data, and a chronological evaluation. It is separate from workspace forecasts and the inventory modeller.

## Deploying for invited kitchens

Run `npm run build`, then serve the built site and `/api` from the same FastAPI server. A multi-stage `Dockerfile` is included. Configure HTTPS in front of FastAPI and set `YLD_PUBLIC_URL` to that exact HTTPS origin. Set `DATABASE_URL` to the restricted Postgres connection string for the private `yld` schema; apply the checked-in Supabase migrations, including the password migration, before deploying the new API. Set `YLD_ENV=production` for fail-fast checks of these settings and the Resend credentials. Local development can omit `DATABASE_URL` and use SQLite at `YLD_DB_PATH`. Keep `.env` and database credentials out of source control.

The temporary Vercel deployment serves the Vite frontend at `https://yld-drab.vercel.app`. Its `vercel.json` routes `/api/*` over HTTPS to `https://yld.nz/api/*`, so accounts and service data remain on the VM backend. The `.vercelignore` excludes the Python API and local databases from this static deployment. Invite emails use `YLD_PUBLIC_URL=https://yld.nz`, so their links open the primary domain. Future Git-attributed Vercel deployments require the commit author to have access to the Vercel team; the initial temporary release was deployed from a clean source snapshot through the CLI.

Before inviting businesses, publish the seller's identity, address and contact email in the legal pages; confirm the hosting and Resend privacy disclosures; and test the live invite, password setup, sign-in, import, plan and sign-out flow. This site does not take live payment. See [LEGAL_LAUNCH_CHECKLIST.md](LEGAL_LAUNCH_CHECKLIST.md).

### Stripe test checkout

The Local and Multi-chain pricing buttons can open Stripe-hosted subscription Checkout in **test mode only**. Set `YLD_STRIPE_TEST_CHECKOUT=1`, a `sk_test_` `STRIPE_SECRET_KEY`, a `whsec_` `STRIPE_WEBHOOK_SECRET`, and two monthly recurring test Price IDs (`STRIPE_PRICE_LOCAL` and `STRIPE_PRICE_MULTI_CHAIN`) on the FastAPI server. All five settings are required; without them the page keeps its sign-in buttons. Use the price amounts and currency shown on the pricing page when creating Stripe Prices, and verify tax settings in Stripe. Do not put the secret key in Vite or Vercel frontend environment variables.

Register the webhook URL `https://yld.nz/api/billing/webhook` in the Stripe test dashboard for `customer.subscription.created`, `customer.subscription.updated`, and `customer.subscription.deleted`. The current Vercel frontend proxies `/api/*` to that backend. Apply the `stripe_test_billing` Supabase migration before enabling checkout on Postgres; local SQLite creates its table automatically. A workspace owner can open the Stripe test customer portal after Stripe sends a subscription webhook. Configure the portal in Stripe test mode first.

Checkout, the customer portal, and webhook processing are restricted to test keys. Apply the `workspace_checkout_reservations` migration before deploying this checkout flow on Postgres. An open Checkout Session is reused for repeated requests; returning through Stripe's cancel link closes it so another plan can be selected. If Stripe confirmation is delayed, the pricing page offers a status recheck without opening a second checkout. Subscription status is displayed on pricing but does not yet gate product access. Enterprise remains a proposed custom plan. Before any live payment launch, finalize the plans and implemented features, legal operator and billing terms, tax treatment, cancellation flow, webhook and portal behavior, and the production key setup.

## Verification

```bash
npm run build
PYTHONDONTWRITEBYTECODE=1 uv run --locked python -m unittest discover -s tests -v
```
