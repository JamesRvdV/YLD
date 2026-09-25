# YLD

Invite-only restaurant prep planner built with Vite, React and FastAPI. Every invited workspace starts with 84 fictional services and has separate accounts, dishes and service history. One-use links provide access; there is no shared demo password.

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

## Create your first demo invite

For local development, generate a one-use link without sending email:

```bash
.venv/bin/python -m api.invite --email you@example.com --workspace 'Sales Demo' --local-link
```

Open the printed link in the browser. Invitations expire in 48 hours and can be used once. After sign-in, sessions last seven days. Existing users can request a 15-minute sign-in link from `/login`.

For real email, set `RESEND_API_KEY`, `YLD_EMAIL_FROM` and the public `YLD_PUBLIC_URL`, then omit `--local-link`:

```bash
.venv/bin/python -m api.invite --email chef@example.com --workspace 'Example Kitchen'
```

`YLD_EMAIL_FROM` must use a [verified Resend sending domain](https://resend.com/docs/dashboard/domains/introduction). The server uses [Resend's email API](https://resend.com/docs/api-reference/emails/send-email) for transactional invitations. No key is sent to the browser. To add another person to an existing kitchen, use `--workspace-id ID` instead of `--workspace`; the owner can read the workspace ID from `/api/auth/me` while signed in.

## Sales demo flow

1. Open the invited account. It has its own isolated fictional sample kitchen.
2. Show tomorrow's auto-estimated covers and dish-by-dish prep quantities.
3. In **Menu costs**, change one sample ingredient cost and show the recalculated plan.
4. Log a sample prepared/sold actual and review **History**.
5. The owner can use **Reset sample data** before the next presentation. This permanently removes changes in that workspace.

To show a real-data onboarding path, open **Import CSV** and download the fictional example file. Upload it to preview dish and service counts, then confirm the replacement. The import accepts one row per dish and service with `date,dish,sold,covers,ingredient_cost,price`; `prepared` and `category` are optional. Waste comparisons only appear when prepared counts are present. Import replaces all dishes and history in that workspace, so download **Current data** first or use a separate demo workspace when showing the flow. The owner can reset to fictional sample data afterwards.

Forecasts use up to 56 earlier services in a weighted ridge regression. Covers become automatic after 14 recorded service days. History shows a 28-service walk-forward comparison using only data available before each service. Sample figures are illustrative, not proven customer savings.

## Deploying for invited pilots

Run `npm run build`, then serve the built site and `/api` from the same persistent FastAPI server. A multi-stage `Dockerfile` is included. Configure HTTPS in front of FastAPI, set `YLD_PUBLIC_URL` to that exact HTTPS origin, and set `YLD_DB_PATH` to an **absolute path on durable storage** with backups. Set `YLD_ENV=production` for fail-fast checks of these settings and the Resend credentials; the container sets it automatically. If using the container, mount durable storage at `/data`. This SQLite setup is for one persistent server; do not deploy it to ephemeral serverless functions. The login cookie is marked Secure when `YLD_PUBLIC_URL` uses HTTPS. Keep `.env` and the database out of source control.

Before inviting real businesses, publish the seller's identity, address and contact email in the legal pages; confirm the hosting and Resend privacy disclosures; and test the live invite, sign-in, planner, reset and sign-out flow. This site does not take payment or create subscriptions. See [LEGAL_LAUNCH_CHECKLIST.md](LEGAL_LAUNCH_CHECKLIST.md).

## Verification

```bash
npm run build
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```
