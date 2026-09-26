from __future__ import annotations

import math
import csv
import io
import os
import sqlite3
import psycopg
import stripe
from psycopg.rows import dict_row
import hashlib
import json
import logging
import re
import secrets
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from statistics import NormalDist, pstdev
from typing import Optional
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from api.modeling import MIN_SERVICES, cover_estimate, predict as predict_trained, supported as trained_supported, validate_artifact
from api import import_mapping

DB_PATH = Path(os.getenv("YLD_DB_PATH", Path(__file__).parent / "yld.db"))
DATABASE_URL = os.getenv("DATABASE_URL")
if os.getenv("YLD_REQUIRE_POSTGRES") == "1" and not DATABASE_URL:
    raise RuntimeError("YLD_REQUIRE_POSTGRES requires DATABASE_URL")
PUBLIC_URL = os.getenv("YLD_PUBLIC_URL", "http://127.0.0.1:5173").rstrip("/")
SESSION_SECONDS = 7 * 24 * 60 * 60
LINK_SECONDS = 48 * 60 * 60
COOKIE_NAME = "yld_session"
ADMIN_EMAIL = "axel.mckenna7@gmail.com"
BUSINESS_TZ = ZoneInfo("Pacific/Auckland")
if os.getenv("YLD_ENV") == "production":
    if not PUBLIC_URL.startswith("https://") or (not DATABASE_URL and not DB_PATH.is_absolute()) or not os.getenv("RESEND_API_KEY") or not os.getenv("YLD_EMAIL_FROM"):
        raise RuntimeError("Production requires HTTPS YLD_PUBLIC_URL, DATABASE_URL or absolute YLD_DB_PATH, RESEND_API_KEY and YLD_EMAIL_FROM")
app = FastAPI(title="YLD Prep Planner API", version="1.0")
logger = logging.getLogger("yld.auth")

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if PUBLIC_URL.startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response

def local_today() -> date:
    return datetime.now(BUSINESS_TZ).date()

@contextmanager
def db():
    if DATABASE_URL:
        conn = PostgresConnection(DATABASE_URL)
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

class PostgresConnection:
    """Keep existing parameterized queries while moving the backend to Postgres."""

    def __init__(self, url: str):
        self.connection = psycopg.connect(url, row_factory=dict_row, connect_timeout=5, sslmode="require")
        self.connection.execute("SET search_path TO yld")

    def execute(self, query, params=None):
        return self.connection.execute(query.replace("?", "%s"), params)

    def executemany(self, query, params):
        with self.connection.cursor() as cursor:
            cursor.executemany(query.replace("?", "%s"), params)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()

def init_db():
    if DATABASE_URL:
        with db() as conn:
            conn.execute("SELECT 1 FROM workspaces LIMIT 1")
        return
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id), email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, role TEXT NOT NULL, activated_at INTEGER, password_hash TEXT, failed_logins INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS workspace_dishes (workspace_id TEXT NOT NULL REFERENCES workspaces(id), id TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL, ingredient_cost REAL NOT NULL, baseline INTEGER NOT NULL, shortage_cost REAL NOT NULL, description TEXT NOT NULL, PRIMARY KEY(workspace_id,id));
        CREATE TABLE IF NOT EXISTS workspace_history (workspace_id TEXT NOT NULL REFERENCES workspaces(id), day TEXT NOT NULL, dish_id TEXT NOT NULL, sold INTEGER NOT NULL, prepared INTEGER NOT NULL, leftover INTEGER NOT NULL, covers INTEGER NOT NULL, PRIMARY KEY(workspace_id,day,dish_id), FOREIGN KEY(workspace_id,dish_id) REFERENCES workspace_dishes(workspace_id,id));
        CREATE TABLE IF NOT EXISTS auth_links (token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), kind TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER, created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS auth_links_account ON auth_links(account_id,created_at);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS sessions_account ON sessions(account_id);
        CREATE TABLE IF NOT EXISTS workspace_billing (workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id), stripe_customer_id TEXT NOT NULL UNIQUE, stripe_subscription_id TEXT NOT NULL UNIQUE, plan TEXT NOT NULL CHECK(plan IN ('local','multi_chain')), status TEXT NOT NULL, last_event_created INTEGER NOT NULL, updated_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS workspace_checkout (workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id), plan TEXT NOT NULL CHECK(plan IN ('local','multi_chain')), idempotency_key TEXT NOT NULL, session_id TEXT, session_url TEXT, expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS waitlist_signups (email TEXT PRIMARY KEY, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS model_jobs (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id), status TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'queued', created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER, data_hash TEXT, reason TEXT, metrics_json TEXT);
        CREATE INDEX IF NOT EXISTS model_jobs_workspace ON model_jobs(workspace_id,created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS model_jobs_one_pending ON model_jobs(workspace_id) WHERE status IN ('queued','running');
        CREATE TABLE IF NOT EXISTS model_versions (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id), status TEXT NOT NULL, artifact_json TEXT NOT NULL, metrics_json TEXT NOT NULL, data_hash TEXT NOT NULL, created_at INTEGER NOT NULL, activated_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS model_versions_workspace ON model_versions(workspace_id,status,created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS model_versions_one_active ON model_versions(workspace_id) WHERE status='active';
        CREATE TABLE IF NOT EXISTS workspace_import_mappings (workspace_id TEXT NOT NULL REFERENCES workspaces(id), source_signature TEXT NOT NULL, mapping_json TEXT NOT NULL, updated_at INTEGER NOT NULL, PRIMARY KEY(workspace_id,source_signature));
        """)
        if "data_mode" not in {row[1] for row in conn.execute("PRAGMA table_info(workspaces)")}:
            conn.execute("ALTER TABLE workspaces ADD COLUMN data_mode TEXT NOT NULL DEFAULT 'empty'")
        if "stage" not in {row[1] for row in conn.execute("PRAGMA table_info(model_jobs)")}:
            conn.execute("ALTER TABLE model_jobs ADD COLUMN stage TEXT NOT NULL DEFAULT 'queued'")
        account_columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
        if "password_hash" not in account_columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN password_hash TEXT")
        if "failed_logins" not in account_columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN failed_logins INTEGER NOT NULL DEFAULT 0")
        if "locked_until" not in account_columns:
            conn.execute("ALTER TABLE accounts ADD COLUMN locked_until INTEGER NOT NULL DEFAULT 0")
        if "prep_known" not in {row[1] for row in conn.execute("PRAGMA table_info(workspace_history)")}:
            conn.execute("ALTER TABLE workspace_history ADD COLUMN prep_known INTEGER NOT NULL DEFAULT 1")
        # Earlier workspaces had generated menu and service rows. They must
        # start empty; the CSV import is the only source of history.
        conn.execute("DELETE FROM workspace_history WHERE workspace_id IN (SELECT id FROM workspaces WHERE data_mode='sample')")
        conn.execute("DELETE FROM workspace_dishes WHERE workspace_id IN (SELECT id FROM workspaces WHERE data_mode='sample')")
        conn.execute("UPDATE workspaces SET data_mode='empty' WHERE data_mode='sample'")
        for legacy_table in ("service_notes", "service_history", "dishes", "users"):
            conn.execute(f"DROP TABLE IF EXISTS {legacy_table}")

def parse_sales_csv(csv_text: str):
    """One row per dish and service. Validate everything before replacing any data."""
    if len(csv_text.encode("utf-8")) > 2_000_000:
        raise HTTPException(413, "CSV must be smaller than 2 MB")
    try:
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff"), newline=""))
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        aliases = {"service_date": "day", "date": "day", "day": "day", "dish": "dish", "item": "dish", "dish_name": "dish", "units_sold": "sold", "sold": "sold", "covers": "covers", "prepared": "prepared", "ingredient_cost": "ingredient_cost", "price": "price", "category": "category"}
        headers = {name.strip().lower(): name for name in reader.fieldnames if name is not None}
        columns = {canonical: next((headers[alias] for alias, target in aliases.items() if target == canonical and alias in headers), None) for canonical in set(aliases.values())}
        missing = [name for name in ("day", "dish", "sold", "covers") if not columns[name]]
        if missing:
            raise ValueError("Missing columns: " + ", ".join(missing))
        dishes, rows, seen, daily_covers = {}, [], set(), {}
        for line_number, raw in enumerate(reader, start=2):
            if line_number > 20001:
                raise ValueError("CSV may contain at most 20,000 data rows")
            if None in raw or not any((value or "").strip() for value in raw.values()):
                if None in raw:
                    raise ValueError(f"Row {line_number}: too many columns")
                continue
            def cell(name):
                return (raw.get(columns[name]) or "").strip() if columns[name] else ""
            def whole(name, minimum):
                value = cell(name)
                if not re.fullmatch(r"\d+", value) or int(value) < minimum:
                    raise ValueError(f"Row {line_number}: {name} must be a whole number of at least {minimum}")
                return int(value)
            def money_value(name):
                value = cell(name)
                if not value:
                    return None
                try:
                    number = float(value)
                except ValueError:
                    number = -1
                if not math.isfinite(number) or number <= 0 or number > 10000:
                    raise ValueError(f"Row {line_number}: {name} must be a positive amount")
                return round(number, 2)
            try:
                day = date.fromisoformat(cell("day"))
            except ValueError:
                raise ValueError(f"Row {line_number}: date must be YYYY-MM-DD") from None
            if day > local_today():
                raise ValueError(f"Row {line_number}: future services cannot be imported")
            name = cell("dish")
            if not name or len(name) > 120:
                raise ValueError(f"Row {line_number}: dish must be 1–120 characters")
            dish_key = name.casefold()
            sold = whole("sold", 0)
            covers = whole("covers", 1)
            prepared_text = cell("prepared")
            prep_known = bool(prepared_text)
            prepared = whole("prepared", 0) if prep_known else sold
            if sold > prepared:
                raise ValueError(f"Row {line_number}: sold cannot exceed prepared")
            ingredient_cost = money_value("ingredient_cost")
            price = money_value("price")
            category = cell("category") or "MENU"
            if len(category) > 60:
                raise ValueError(f"Row {line_number}: category is too long")
            if (day, dish_key) in seen:
                raise ValueError(f"Row {line_number}: duplicate dish and date")
            seen.add((day, dish_key))
            if day in daily_covers and daily_covers[day] != covers:
                raise ValueError(f"Row {line_number}: covers must match for all dishes on a date")
            daily_covers[day] = covers
            if dish_key not in dishes:
                dishes[dish_key] = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, dish_key)), "name": name, "category": category.upper(), "ingredient_cost": None, "price": None}
            dish = dishes[dish_key]
            for field, amount in (("ingredient_cost", ingredient_cost), ("price", price)):
                if amount is not None:
                    if dish[field] is not None and dish[field] != amount:
                        raise ValueError(f"Row {line_number}: {field} for {name} differs across rows")
                    dish[field] = amount
            if dish["price"] is not None and dish["ingredient_cost"] is not None and dish["price"] <= dish["ingredient_cost"]:
                raise ValueError(f"Row {line_number}: price must exceed ingredient_cost")
            rows.append({"day": day.isoformat(), "dish_key": dish_key, "sold": sold, "prepared": prepared, "leftover": prepared - sold, "covers": covers, "prep_known": int(prep_known)})
        if not rows:
            raise ValueError("CSV has no service rows")
        if len(dishes) > 100:
            raise ValueError("CSV may contain at most 100 dishes")
        return dishes, rows, daily_covers
    except csv.Error as error:
        raise HTTPException(400, f"Invalid CSV: {error}") from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error

init_db()

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256:600000:{salt.hex()}:{digest.hex()}"

DUMMY_PASSWORD_HASH = hash_password("unused-dummy-password")

def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        algorithm, rounds, salt, expected = stored.split(":")
        if algorithm != "pbkdf2_sha256" or int(rounds) != 600_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return secrets.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False

def is_admin(email: str) -> bool:
    return email == ADMIN_EMAIL

def clean_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Enter a valid email address")
    return email

def invite_url(token: str) -> str:
    # A fragment keeps the secret out of ordinary web-server request logs.
    return f"{PUBLIC_URL}/invite#{urlencode({'token': token})}"

def send_link_email(email: str, workspace_name: str, link: str, kind: str, link_id: str):
    api_key = os.getenv("RESEND_API_KEY")
    sender = os.getenv("YLD_EMAIL_FROM")
    if not api_key or not sender:
        raise RuntimeError("Set RESEND_API_KEY and YLD_EMAIL_FROM before sending invitations")
    if not PUBLIC_URL.startswith("https://") and not PUBLIC_URL.startswith(("http://localhost:", "http://127.0.0.1:")):
        raise RuntimeError("YLD_PUBLIC_URL must use HTTPS outside local development")
    action = "Set your YLD password"
    minutes = "48 hours"
    payload = {
        "from": sender,
        "to": [email],
        "subject": f"{action} to YLD",
        "html": f'<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;padding:32px;color:#171717"><h1>YLD.</h1><p>{escape(action)} to {escape(workspace_name)}.</p><p><a href="{escape(link, quote=True)}" style="display:inline-block;padding:14px 20px;background:#171717;color:#fff;text-decoration:none">Open your kitchen →</a></p><p>This link expires in {minutes} and works once. If you did not expect it, you can ignore this email.</p></div>',
        "text": f"{action} to {workspace_name}: {link}\n\nThis one-use link expires in {minutes}.",
    }
    request = UrlRequest(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "User-Agent": f"YLD/1.0 (+{PUBLIC_URL})", "Idempotency-Key": link_id},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as result:
            if result.status not in (200, 201):
                raise RuntimeError("Resend did not accept the email")
    except (HTTPError, URLError) as error:
        raise RuntimeError("Resend could not send the email; check the sender domain and API key") from error

def issue_invite(email: str, workspace_name: Optional[str] = None, workspace_id: Optional[str] = None, send: bool = True) -> str:
    """Trusted server-side operation; intentionally not exposed as a public route."""
    email = clean_email(email)
    if bool(workspace_name) == bool(workspace_id):
        raise ValueError("Provide exactly one of workspace_name or workspace_id")
    if workspace_name:
        workspace_name = workspace_name.strip()
        if not workspace_name or len(workspace_name) > 120:
            raise ValueError("Workspace name must be 1–120 characters")
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    link_id = str(uuid.uuid4())
    with db() as conn:
        existing = conn.execute("SELECT a.id,a.workspace_id,w.name AS workspace_name FROM accounts a JOIN workspaces w ON w.id=a.workspace_id WHERE a.email=?", (email,)).fetchone()
        if workspace_name:
            if existing:
                if existing["workspace_name"] != workspace_name:
                    raise ValueError("That email already belongs to another workspace")
                workspace_id = existing["workspace_id"]
            else:
                workspace_id = str(uuid.uuid4())
                conn.execute("INSERT INTO workspaces(id,name,created_at,data_mode) VALUES (?,?,?,'empty')", (workspace_id, workspace_name, now))
            role = "owner"
        else:
            workspace = conn.execute("SELECT name FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            if not workspace:
                raise ValueError("Workspace not found")
            workspace_name = workspace["name"]
            if existing and existing["workspace_id"] != workspace_id:
                raise ValueError("That email belongs to another workspace")
            role = "member"
        if existing:
            account_id = existing["id"]
        else:
            account_id = str(uuid.uuid4())
            conn.execute("INSERT INTO accounts(id,workspace_id,email,name,role,activated_at) VALUES (?,?,?,?,?,NULL)", (account_id, workspace_id, email, email.split('@')[0], role))
        conn.execute("INSERT INTO auth_links VALUES (?,?,?,?,NULL,?)", (token_hash(token), account_id, "invite", now + LINK_SECONDS, now))
    link = invite_url(token)
    if send:
        try:
            send_link_email(email, workspace_name, link, "invite", link_id)
        except Exception:
            with db() as conn:
                conn.execute("DELETE FROM auth_links WHERE token_hash=?", (token_hash(token),))
            raise
    return link

def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Sign in to continue")
    with db() as conn:
        row = conn.execute("""SELECT a.id,a.email,a.name,a.role,a.workspace_id,w.name AS workspace_name,w.data_mode,s.csrf_token
            FROM sessions s JOIN accounts a ON a.id=s.account_id JOIN workspaces w ON w.id=a.workspace_id
            WHERE s.token_hash=? AND s.expires_at>? AND a.activated_at IS NOT NULL""", (token_hash(token), int(time.time()))).fetchone()
    if not row:
        raise HTTPException(401, "Session expired; sign in again")
    return dict(row)

def require_csrf(request: Request, user: dict = Depends(current_user)) -> dict:
    if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), user["csrf_token"]):
        raise HTTPException(403, "Invalid session request")
    return user

def public_user(user: dict) -> dict:
    return {**{key: user[key] for key in ("id", "email", "name", "role", "workspace_id", "workspace_name", "csrf_token", "data_mode")}, "is_admin": is_admin(user["email"])}

def stripe_test_ready() -> bool:
    return (os.getenv("YLD_STRIPE_TEST_CHECKOUT") == "1"
            and os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_test_")
            and os.getenv("STRIPE_WEBHOOK_SECRET", "").startswith("whsec_")
            and all(os.getenv(name, "").startswith("price_") for name in ("STRIPE_PRICE_LOCAL", "STRIPE_PRICE_MULTI_CHAIN")))

def billing_owner(user: dict = Depends(require_csrf)) -> dict:
    if user["role"] != "owner":
        raise HTTPException(403, "Only a workspace owner can manage billing")
    return user

class CheckoutInput(BaseModel):
    plan: str

@app.get("/api/billing/config")
def billing_config():
    return {"test_checkout_enabled": stripe_test_ready()}

@app.get("/api/billing/status")
def billing_status(user: dict = Depends(current_user)):
    with db() as conn:
        row = conn.execute("SELECT plan,status FROM workspace_billing WHERE workspace_id=?", (user["workspace_id"],)).fetchone()
    return {"billing": dict(row) if row else None}

@app.post("/api/billing/checkout")
def billing_checkout(payload: CheckoutInput, user: dict = Depends(billing_owner)):
    if not stripe_test_ready():
        raise HTTPException(503, "Stripe test checkout is not configured")
    price = {"local": os.getenv("STRIPE_PRICE_LOCAL"), "multi_chain": os.getenv("STRIPE_PRICE_MULTI_CHAIN")}.get(payload.plan)
    if not price:
        raise HTTPException(400, "Choose an available plan")
    now = int(time.time())
    reservation_key = str(uuid.uuid4())
    with db() as conn:
        existing = conn.execute("SELECT status FROM workspace_billing WHERE workspace_id=?", (user["workspace_id"],)).fetchone()
        if existing and existing["status"] != "canceled":
            raise HTTPException(409, "This workspace already has a subscription. Manage it in Stripe.")
        conn.execute("DELETE FROM workspace_checkout WHERE workspace_id=? AND expires_at<=?", (user["workspace_id"], now))
        reserved = conn.execute("INSERT INTO workspace_checkout(workspace_id,plan,idempotency_key,session_id,session_url,expires_at) VALUES (?,?,?,?,?,?) ON CONFLICT(workspace_id) DO NOTHING", (user["workspace_id"], payload.plan, reservation_key, None, None, now + 24 * 3600))
        if reserved.rowcount != 1:
            pending = conn.execute("SELECT plan,idempotency_key,session_url FROM workspace_checkout WHERE workspace_id=?", (user["workspace_id"],)).fetchone()
            if pending["plan"] != payload.plan:
                raise HTTPException(409, "Another plan's checkout is open. Finish it or wait for it to expire.")
            if pending["session_url"]:
                return {"url": pending["session_url"]}
            reservation_key = pending["idempotency_key"]
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            client_reference_id=user["workspace_id"],
            customer_email=user["email"],
            success_url=f"{PUBLIC_URL}/pricing?checkout=success",
            cancel_url=f"{PUBLIC_URL}/pricing?checkout=cancel",
            metadata={"workspace_id": user["workspace_id"], "plan": payload.plan},
            subscription_data={"metadata": {"workspace_id": user["workspace_id"], "plan": payload.plan}},
            idempotency_key=reservation_key,
        )
        with db() as conn:
            conn.execute("UPDATE workspace_checkout SET session_id=?,session_url=?,expires_at=? WHERE workspace_id=? AND idempotency_key=?", (session.id, session.url, session.expires_at, user["workspace_id"], reservation_key))
    except Exception:
        logger.exception("Stripe test checkout could not be created")
        raise HTTPException(502, "Could not open Stripe checkout") from None
    return {"url": session.url}

@app.post("/api/billing/checkout/abandon")
def billing_checkout_abandon(user: dict = Depends(billing_owner)):
    if not stripe_test_ready():
        raise HTTPException(503, "Stripe test checkout is not configured")
    with db() as conn:
        pending = conn.execute("SELECT idempotency_key,session_id FROM workspace_checkout WHERE workspace_id=?", (user["workspace_id"],)).fetchone()
    if not pending:
        return {"ok": True}
    if not pending["session_id"]:
        raise HTTPException(409, "Checkout is still opening. Try again shortly.")
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    try:
        session = stripe.checkout.Session.retrieve(pending["session_id"])
        if session.status == "complete":
            raise HTTPException(409, "Checkout completed. Wait for Stripe to confirm the subscription.")
        if session.status == "open":
            stripe.checkout.Session.expire(pending["session_id"])
    except HTTPException:
        raise
    except Exception:
        logger.exception("Stripe test checkout could not be abandoned")
        raise HTTPException(502, "Could not cancel the open checkout") from None
    with db() as conn:
        conn.execute("DELETE FROM workspace_checkout WHERE workspace_id=? AND idempotency_key=?", (user["workspace_id"], pending["idempotency_key"]))
    return {"ok": True}

def record_subscription(subscription, created: int, source: str):
    metadata = subscription.get("metadata") or {}
    workspace_id, plan = metadata.get("workspace_id"), metadata.get("plan")
    customer_id, subscription_id = subscription.get("customer"), subscription.get("id")
    if not all((workspace_id, plan in ("local", "multi_chain"), customer_id, subscription_id)):
        logger.error("Stripe subscription missing YLD metadata: %s", source)
        raise HTTPException(400, "Subscription metadata is incomplete")
    with db() as conn:
        workspace = conn.execute("SELECT id FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        if not workspace:
            raise HTTPException(400, "Unknown workspace")
        existing = conn.execute("SELECT stripe_subscription_id,status,last_event_created FROM workspace_billing WHERE workspace_id=?", (workspace_id,)).fetchone()
        if existing and existing["stripe_subscription_id"] != subscription_id and existing["status"] != "canceled":
            logger.error("Conflicting Stripe subscriptions for workspace %s", workspace_id)
            raise HTTPException(409, "Workspace has another subscription")
        if not existing or (existing["stripe_subscription_id"] != subscription_id and existing["status"] == "canceled") or created >= existing["last_event_created"]:
            conn.execute("""INSERT INTO workspace_billing(workspace_id,stripe_customer_id,stripe_subscription_id,plan,status,last_event_created,updated_at)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET stripe_customer_id=excluded.stripe_customer_id,
                stripe_subscription_id=excluded.stripe_subscription_id,plan=excluded.plan,status=excluded.status,
                last_event_created=excluded.last_event_created,updated_at=excluded.updated_at""",
                (workspace_id, customer_id, subscription_id, plan, subscription["status"], created, int(time.time())))
            conn.execute("DELETE FROM workspace_checkout WHERE workspace_id=?", (workspace_id,))
    return workspace_id

@app.post("/api/billing/checkout/verify")
def billing_checkout_verify(user: dict = Depends(billing_owner)):
    if not stripe_test_ready():
        raise HTTPException(503, "Stripe test checkout is not configured")
    with db() as conn:
        pending = conn.execute("SELECT session_id FROM workspace_checkout WHERE workspace_id=?", (user["workspace_id"],)).fetchone()
        billing = conn.execute("SELECT plan,status FROM workspace_billing WHERE workspace_id=?", (user["workspace_id"],)).fetchone()
    if billing and billing["status"] != "canceled":
        return {"billing": dict(billing), "checkout": "complete"}
    if not pending or not pending["session_id"]:
        return {"billing": dict(billing) if billing else None, "checkout": "unavailable"}
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    try:
        session = stripe.checkout.Session.retrieve(pending["session_id"])
        if session.status == "expired":
            with db() as conn:
                conn.execute("DELETE FROM workspace_checkout WHERE workspace_id=? AND session_id=?", (user["workspace_id"], pending["session_id"]))
            return {"billing": None, "checkout": "expired"}
        if session.status == "complete" and not session.subscription:
            return {"billing": None, "checkout": "pending"}
        if session.status != "complete":
            return {"billing": None, "checkout": "open", "url": session.url}
        subscription = stripe.Subscription.retrieve(session.subscription)
    except Exception:
        logger.exception("Stripe test checkout could not be verified")
        raise HTTPException(502, "Could not check Stripe checkout") from None
    if subscription.get("livemode") or (subscription.get("metadata") or {}).get("workspace_id") != user["workspace_id"]:
        raise HTTPException(400, "Stripe subscription does not match this workspace")
    record_subscription(subscription, int(subscription["created"]), subscription["id"])
    return {"billing": {"plan": subscription["metadata"]["plan"], "status": subscription["status"]}, "checkout": "complete"}

@app.post("/api/billing/portal")
def billing_portal(user: dict = Depends(billing_owner)):
    if not stripe_test_ready():
        raise HTTPException(503, "Stripe test billing is not configured")
    with db() as conn:
        row = conn.execute("SELECT stripe_customer_id FROM workspace_billing WHERE workspace_id=?", (user["workspace_id"],)).fetchone()
    if not row:
        raise HTTPException(404, "No subscription for this workspace")
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    try:
        session = stripe.billing_portal.Session.create(customer=row["stripe_customer_id"], return_url=f"{PUBLIC_URL}/pricing")
    except Exception:
        logger.exception("Stripe test billing portal could not be created")
        raise HTTPException(502, "Could not open Stripe billing") from None
    return {"url": session.url}

@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    if not stripe_test_ready():
        raise HTTPException(503, "Stripe test billing is not configured")
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(await request.body(), signature, os.environ["STRIPE_WEBHOOK_SECRET"])
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(400, "Invalid Stripe signature") from None
    if event.get("livemode"):
        raise HTTPException(400, "Live Stripe events are not accepted")
    if event["type"] not in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"):
        return {"received": True}
    record_subscription(event["data"]["object"], int(event["created"]), event["id"])
    return {"received": True}

def history(conn, workspace_id: str, dish_id: str):
    return [dict(r) for r in conn.execute("SELECT * FROM workspace_history WHERE workspace_id=? AND dish_id=? ORDER BY day", (workspace_id, dish_id))]

def service_summary(conn, workspace_id: str, service_day: date):
    """Roll up the actuals logged for one service without requiring a new table."""
    rows = [dict(row) for row in conn.execute("""SELECT d.id,d.name,d.ingredient_cost,
        h.covers,h.prepared,h.sold,h.leftover,h.prep_known
        FROM workspace_dishes d
        LEFT JOIN workspace_history h ON h.workspace_id=d.workspace_id AND h.dish_id=d.id AND h.day=?
        WHERE d.workspace_id=? ORDER BY d.name""", (service_day.isoformat(), workspace_id))]
    logged = [row for row in rows if row["prep_known"]]
    covers = next((row["covers"] for row in logged if row["covers"] is not None), None)
    prepared = sum(row["prepared"] for row in logged)
    sold = sum(row["sold"] for row in logged)
    leftovers = sum(row["leftover"] for row in logged)
    ingredient_waste = sum(row["leftover"] * row["ingredient_cost"] for row in logged)
    return {
        "day": service_day.isoformat(),
        "covers": covers,
        "total_dishes": len(rows),
        "logged_dishes": len(logged),
        "complete": bool(rows) and len(logged) == len(rows),
        "prepared": prepared,
        "sold": sold,
        "leftovers": leftovers,
        "ingredient_waste": round(ingredient_waste, 2),
        "dishes": [{"id": row["id"], "name": row["name"], "prepared": row["prepared"], "sold": row["sold"], "leftover": row["leftover"]} for row in logged],
    }

def solve_ridge(samples, outcomes, weights, penalty=2.0):
    """Small weighted ridge fit, solved by pivoted Gaussian elimination."""
    size = len(samples[0])
    matrix = [[0.0] * (size + 1) for _ in range(size)]
    for features, target, weight in zip(samples, outcomes, weights):
        for i in range(size):
            matrix[i][-1] += weight * features[i] * target
            for j in range(size):
                matrix[i][j] += weight * features[i] * features[j]
    for i in range(1, size):
        matrix[i][i] += penalty
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(matrix[row][col]))
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        if abs(matrix[col][col]) < 1e-9:
            continue
        scale = matrix[col][col]
        matrix[col] = [value / scale for value in matrix[col]]
        for row in range(size):
            if row == col:
                continue
            factor = matrix[row][col]
            matrix[row] = [a - factor*b for a, b in zip(matrix[row], matrix[col])]
    return [matrix[i][-1] for i in range(size)]

def forecast(rows, target_covers, target_day, event_boost):
    # Weighted ridge regression on covers, weekend pattern and recent trend.
    recent = [row for row in rows if date.fromisoformat(row["day"]) < target_day][-56:]
    if not recent:
        return 0.0, 1.0
    features, weights, outcomes = [], [], []
    for idx, row in enumerate(recent):
        weekday = date.fromisoformat(row["day"]).weekday()
        weights.append(math.exp((idx - len(recent) + 1) / 28) * (1.3 if weekday == target_day.weekday() else 1))
        features.append([1.0, row["covers"] / 75, float(weekday in (4, 5)), idx / max(1, len(recent)-1)])
        outcomes.append(row["sold"])
    coefficients = solve_ridge(features, outcomes, weights)
    target = [1.0, target_covers / 75, float(target_day.weekday() in (4, 5)), 1.0]
    predicted = max(0, sum(a*b for a, b in zip(coefficients, target))) * (1 + event_boost / 100)
    residuals = [y - sum(a*b for a, b in zip(coefficients, x)) for x, y in zip(features, outcomes)]
    uncertainty = max(1.8, pstdev(residuals) if len(residuals) > 1 else 2.0)
    return predicted, uncertainty

def forecast_covers(conn, workspace_id, target_day):
    """Estimate covers from completed services once two weeks of history exist."""
    services = [dict(row) for row in conn.execute(
        "SELECT day, ROUND(AVG(covers)) AS covers FROM workspace_history WHERE workspace_id=? AND day < ? GROUP BY day ORDER BY day",
        (workspace_id, target_day.isoformat()),
    )]
    return cover_estimate(services, target_day)

def normal_cdf(x):
    return (1 + math.erf(x / math.sqrt(2))) / 2

def normal_pdf(x):
    return math.exp(-x*x/2) / math.sqrt(2*math.pi)

def optimize(mu, sigma, ingredient_cost, shortage_cost, waste_weight):
    # The newsvendor optimum is the demand quantile where marginal waste and
    # missed-sale costs balance. Check the adjacent whole-portion quantities.
    waste_cost = ingredient_cost * waste_weight
    critical = shortage_cost / (shortage_cost + waste_cost)
    ideal = NormalDist(mu, sigma).inv_cdf(critical)
    quantities = {max(0, math.floor(ideal)), max(0, math.ceil(ideal))}
    candidates = []
    for qty in quantities:
        z = (qty-mu)/sigma
        over = sigma * (normal_pdf(z) + z*normal_cdf(z))
        under = sigma * (normal_pdf(z) - z*(1-normal_cdf(z)))
        cost = over * waste_cost + under * shortage_cost
        candidates.append((cost, qty, over, under))
    return min(candidates)

def backtest(dishes, waste_weight):
    """Walk forward over held-out services using only earlier observations."""
    totals = {"usual_waste": 0.0, "model_waste": 0.0, "observed_missed": 0, "services": 0}
    tested_days = set()
    for dish in dishes:
        rows = dish["history"]
        for idx in range(max(14, len(rows)-28), len(rows)):
            actual = rows[idx]
            if not actual["prep_known"]:
                continue
            mu, sigma = forecast(rows[:idx], actual["covers"], date.fromisoformat(actual["day"]), 0)
            lost_sale_cost = dish["price"] - dish["ingredient_cost"] + dish["shortage_cost"]
            _, qty, _, _ = optimize(mu, sigma, dish["ingredient_cost"], lost_sale_cost, waste_weight)
            # Sales are censored by historic stockouts, so this is a conservative
            # comparison against observed demand, not a claim about unknown demand.
            totals["usual_waste"] += actual["leftover"] * dish["ingredient_cost"]
            totals["model_waste"] += max(0, qty-actual["sold"]) * dish["ingredient_cost"]
            totals["observed_missed"] += max(0, actual["sold"]-qty)
            totals["services"] += 1
            tested_days.add(actual["day"])
    return {"days": len(tested_days), "available": totals["services"] > 0, "usual_waste": round(totals["usual_waste"]) if totals["services"] else None, "model_waste": round(totals["model_waste"]) if totals["services"] else None, "difference": round(totals["usual_waste"]-totals["model_waste"]) if totals["services"] else None, "observed_missed": totals["observed_missed"] if totals["services"] else None}

def build_plan(workspace_id: str, covers: Optional[int], event_boost: int, waste_weight: float):
    tomorrow = local_today() + timedelta(days=1)
    with db() as conn:
        workspace = conn.execute("SELECT data_mode FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        if not workspace or workspace["data_mode"] != "imported":
            raise HTTPException(409, {"code": "import_needed"})
        dishes = [dict(r) for r in conn.execute("SELECT * FROM workspace_dishes WHERE workspace_id=?", (workspace_id,))]
        if not dishes:
            raise HTTPException(409, {"code": "import_needed"})
        estimated_covers, service_days = forecast_covers(conn, workspace_id, tomorrow)
        if covers is None and estimated_covers is None:
            raise HTTPException(409, {"code": "covers_needed", "service_days": service_days, "required_days": 14})
        cover_source = "forecast" if covers is None else "manual"
        covers = estimated_covers if covers is None else covers
        active = conn.execute("SELECT id,artifact_json FROM model_versions WHERE workspace_id=? AND status='active' ORDER BY activated_at DESC LIMIT 1", (workspace_id,)).fetchone()
        trained = {}
        model_version = None
        if active:
            try:
                artifact = validate_artifact(json.loads(active["artifact_json"]), {dish["id"] for dish in dishes})
                trained = {model["dish_id"]: model for model in artifact["models"]}
                model_version = active["id"]
            except (ValueError, TypeError, json.JSONDecodeError):
                logger.error("Invalid active model for workspace %s", workspace_id)
        rows = []
        for dish in dishes:
            h = history(conn, workspace_id, dish["id"])
            model = trained.get(dish["id"])
            if model:
                trained_mu, trained_sigma = predict_trained(model, tomorrow.isoformat(), covers, event_boost)
                if not trained_supported(model, covers, trained_mu):
                    model = None
            mu, sigma = (trained_mu, trained_sigma) if model else forecast(h, covers, tomorrow, event_boost)
            lost_sale_cost = dish["price"] - dish["ingredient_cost"] + dish["shortage_cost"]
            _, qty, expected_leftover, expected_missed = optimize(mu, sigma, dish["ingredient_cost"], lost_sale_cost, waste_weight)
            previous = next((row["prepared"] for row in reversed(h) if row["prep_known"]), None)
            rows.append({**dish, "forecast": round(mu, 1), "forecast_source": "trained" if model else "standard", "confidence_low": max(0, round(mu-1.28*sigma)), "confidence_high": round(mu+1.28*sigma), "prep": qty, "previous_prep": previous, "delta": qty-previous if previous is not None else None, "expected_leftover": round(expected_leftover, 1), "expected_missed": round(expected_missed, 1), "history": h})
        baseline_waste = sum(sum(r["leftover"] * d["ingredient_cost"] for r in d["history"][-28:] if r["prep_known"]) for d in rows)
        known_days = {r["day"] for d in rows for r in d["history"][-28:] if r["prep_known"]}
        expected_waste = sum(d["expected_leftover"] * d["ingredient_cost"] for d in rows)
        baseline_daily = baseline_waste / len(known_days) if known_days else None
        total_units = sum(d["prep"] for d in rows)
        insights = []
        exposure = max(rows, key=lambda d: d["expected_leftover"] * d["ingredient_cost"])
        if exposure["expected_leftover"] >= 0.5:
            insights.append({"title": f"Watch {exposure['name']}", "detail": f"The current plan expects about {exposure['expected_leftover']:.1f} unsold portions, representing roughly ${exposure['expected_leftover'] * exposure['ingredient_cost']:.0f} in ingredient cost."})
        known_prep = [(d, [h for h in d["history"][-14:] if h["prep_known"]]) for d in rows]
        known_prep = [(d, h) for d, h in known_prep if h]
        if known_prep:
            over = max(known_prep, key=lambda pair: sum(h["leftover"] for h in pair[1]))
            portions = sum(h["leftover"] for h in over[1])
            if portions > 0:
                insights.append({"title": f"Recent overpreparation: {over[0]['name']}", "detail": f"Prepared portions exceeded sales by {portions} across the last {len(over[1])} recorded services for this dish. This is not a measurement of discarded food."})
        trend = []
        completed_days = sorted({r["day"] for dish in rows for r in dish["history"] if r["day"] < local_today().isoformat()})[-14:]
        for day in completed_days:
            daily = [r for d in rows for r in d["history"] if r["day"] == day]
            known = [r for r in daily if r["prep_known"]]
            trend.append({"day": day, "label": date.fromisoformat(day).strftime("%d %b"), "waste": round(sum(r["leftover"] * next(x["ingredient_cost"] for x in rows if x["id"] == r["dish_id"]) for r in known)) if known else None, "prepared": sum(r["prepared"] for r in known) if known else None})
        return {"date": tomorrow.isoformat(), "covers": covers, "cover_source": cover_source, "cover_history_days": service_days, "forecast_covers": estimated_covers, "model_version": model_version, "event_boost": event_boost, "waste_weight": waste_weight, "dishes": [{k:v for k,v in d.items() if k != "history"} for d in rows], "insights": insights, "summary": {"prep_units": total_units, "expected_waste": round(expected_waste), "usual_waste": round(baseline_daily) if baseline_daily is not None else None, "waste_reduction": round(max(0, (baseline_daily-expected_waste)/max(1, baseline_daily)*100)) if baseline_daily is not None else None, "at_risk": round(sum(d["expected_missed"] for d in rows), 1)}, "trend": trend, "backtest": backtest(rows, waste_weight)}

class PlanInput(BaseModel):
    covers: Optional[int] = Field(None, ge=1, le=1000)
    event_boost: int = Field(0, ge=-50, le=100)
    waste_weight: float = Field(1.0, ge=0.2, le=3.0)

class ActualInput(BaseModel):
    day: date
    covers: int = Field(ge=1, le=1000)
    dish_id: str
    prepared: int = Field(ge=0)
    sold: int = Field(ge=0)

class EmailInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)

class LoginInput(EmailInput):
    password: str = Field(min_length=1, max_length=256)

class RedeemInput(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=256)

class AdminInviteInput(EmailInput):
    workspace_name: Optional[str] = None
    workspace_id: Optional[str] = None

class DishCostsInput(BaseModel):
    ingredient_cost: float = Field(gt=0, le=10000)
    price: float = Field(gt=0, le=10000)

class SalesCsvInput(BaseModel):
    csv_text: str = Field(min_length=1, max_length=2_000_000)
    menu_costs: dict[str, DishCostsInput] = Field(default_factory=dict)
    train: bool = False
    source_mapping: Optional[dict] = None
    source_signature: Optional[str] = Field(default=None, min_length=64, max_length=64)

class SpreadsheetInput(BaseModel):
    filename: str = Field(min_length=5, max_length=200)
    content_base64: str = Field(min_length=1, max_length=5_400_000)
    use_agent: bool = False

class MappedSpreadsheetInput(SpreadsheetInput):
    mapping: dict

class MappedMenuSpreadsheetInput(SpreadsheetInput):
    mapping: dict

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/waitlist")
def join_waitlist(payload: EmailInput):
    try:
        email = clean_email(payload.email)
    except ValueError:
        raise HTTPException(422, "Enter a valid email address")
    with db() as conn:
        conn.execute("INSERT INTO waitlist_signups(email,created_at) VALUES (?,?) ON CONFLICT(email) DO NOTHING", (email, int(time.time())))
    return {"ok": True}

@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {"user": public_user(user)}

@app.post("/api/auth/login")
def login(payload: LoginInput, response: Response):
    try:
        email = clean_email(payload.email)
    except ValueError:
        raise HTTPException(422, "Enter a valid email address")
    now = int(time.time())
    with db() as conn:
        account = conn.execute("SELECT id,password_hash,failed_logins,locked_until FROM accounts WHERE email=? AND activated_at IS NOT NULL", (email,)).fetchone()
        # Keep the response and password-work similar for unknown addresses.
        valid = verify_password(payload.password, (account["password_hash"] if account else None) or DUMMY_PASSWORD_HASH)
        denied = not account or not account["password_hash"] or not valid or account["locked_until"] > now
        if denied:
            if account and account["locked_until"] <= now:
                failures = account["failed_logins"] + 1
                conn.execute("UPDATE accounts SET failed_logins=?,locked_until=? WHERE id=?", (failures if failures < 5 else 0, now + 15 * 60 if failures >= 5 else 0, account["id"]))
        else:
            conn.execute("UPDATE accounts SET failed_logins=0,locked_until=0 WHERE id=?", (account["id"],))
            session_token = secrets.token_urlsafe(32)
            csrf_token = secrets.token_urlsafe(24)
            conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (token_hash(session_token), account["id"], csrf_token, now + SESSION_SECONDS, now))
    if denied:
        raise HTTPException(401, "Invalid email or password")
    response.set_cookie(COOKIE_NAME, session_token, max_age=SESSION_SECONDS, httponly=True, secure=PUBLIC_URL.startswith("https://"), samesite="lax", path="/")
    return {"ok": True}

@app.get("/api/admin/workspaces")
def admin_workspaces(user: dict = Depends(current_user)):
    if not is_admin(user["email"]):
        raise HTTPException(403, "Admin access required")
    with db() as conn:
        rows = conn.execute("SELECT id,name FROM workspaces ORDER BY name").fetchall()
    return {"workspaces": [dict(row) for row in rows]}

@app.post("/api/admin/invitations")
def admin_invite(payload: AdminInviteInput, user: dict = Depends(require_csrf)):
    if not is_admin(user["email"]):
        raise HTTPException(403, "Admin access required")
    if not os.getenv("RESEND_API_KEY") or not os.getenv("YLD_EMAIL_FROM"):
        raise HTTPException(503, "Invitation email is not configured")
    try:
        issue_invite(payload.email, workspace_name=payload.workspace_name, workspace_id=payload.workspace_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except RuntimeError as error:
        logger.error("Invitation email delivery failed: %s", error)
        raise HTTPException(503, "Invitation email could not be sent") from error
    return {"ok": True}

@app.post("/api/auth/redeem")
def redeem(payload: RedeemInput, response: Response):
    now = int(time.time())
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    with db() as conn:
        link = conn.execute("SELECT account_id FROM auth_links WHERE token_hash=? AND kind='invite' AND used_at IS NULL AND expires_at>?", (token_hash(payload.token), now)).fetchone()
        if not link:
            raise HTTPException(400, "This link has expired or has already been used")
        claimed = conn.execute("UPDATE auth_links SET used_at=? WHERE token_hash=? AND used_at IS NULL", (now, token_hash(payload.token)))
        if claimed.rowcount != 1:
            raise HTTPException(400, "This link has already been used")
        conn.execute("UPDATE accounts SET activated_at=COALESCE(activated_at,?),password_hash=?,failed_logins=0,locked_until=0 WHERE id=?", (now, hash_password(payload.password), link["account_id"]))
        conn.execute("UPDATE auth_links SET used_at=? WHERE account_id=? AND used_at IS NULL", (now, link["account_id"]))
        conn.execute("DELETE FROM sessions WHERE account_id=?", (link["account_id"],))
        conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (token_hash(session_token), link["account_id"], csrf_token, now + SESSION_SECONDS, now))
    response.set_cookie(COOKIE_NAME, session_token, max_age=SESSION_SECONDS, httponly=True, secure=PUBLIC_URL.startswith("https://"), samesite="lax", path="/")
    return {"ok": True}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user: dict = Depends(require_csrf)):
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=? AND account_id=?", (token_hash(request.cookies[COOKIE_NAME]), user["id"]))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}

@app.post("/api/plan")
def plan(payload: PlanInput, user: dict = Depends(current_user)):
    return build_plan(user["workspace_id"], payload.covers, payload.event_boost, payload.waste_weight)

@app.get("/api/models/status")
def model_status(user: dict = Depends(current_user)):
    workspace_id = user["workspace_id"]
    with db() as conn:
        job = conn.execute("SELECT id,status,stage,created_at,finished_at,reason,metrics_json FROM model_jobs WHERE workspace_id=? ORDER BY created_at DESC,id DESC LIMIT 1", (workspace_id,)).fetchone()
        active = conn.execute("SELECT id,created_at,metrics_json FROM model_versions WHERE workspace_id=? AND status='active' ORDER BY activated_at DESC LIMIT 1", (workspace_id,)).fetchone()
        dish_services = [dict(row) for row in conn.execute("SELECT d.name,COUNT(h.day) AS services FROM workspace_dishes d LEFT JOIN workspace_history h ON h.workspace_id=d.workspace_id AND h.dish_id=d.id WHERE d.workspace_id=? GROUP BY d.id,d.name ORDER BY services DESC,d.name", (workspace_id,))]
        counts = [row["services"] for row in dish_services]
    return {"enabled": os.getenv("YLD_MODEL_WORKER_ENABLED") == "1", "job": {"id": job["id"], "status": job["status"], "stage": job["stage"], "created_at": job["created_at"], "finished_at": job["finished_at"], "reason": job["reason"], "metrics": json.loads(job["metrics_json"]) if job["metrics_json"] else None} if job else None,
            "active": {"id": active["id"], "created_at": active["created_at"], "metrics": json.loads(active["metrics_json"])} if active else None,
            "eligible_dishes": sum(count >= MIN_SERVICES for count in counts), "max_services": max(counts, default=0), "required_services": MIN_SERVICES, "dish_services": dish_services[:6]}

@app.post("/api/models/train")
def request_model_training(user: dict = Depends(require_csrf)):
    if os.getenv("YLD_MODEL_WORKER_ENABLED") != "1":
        raise HTTPException(503, "Model training is not configured for this deployment")
    if user["role"] != "owner":
        raise HTTPException(403, "Only the workspace owner can train a model")
    workspace_id = user["workspace_id"]
    now = int(time.time())
    with db() as conn:
        conn.execute("UPDATE workspaces SET data_mode=data_mode WHERE id=?", (workspace_id,))
        eligible = conn.execute("SELECT COUNT(*) AS count FROM (SELECT dish_id FROM workspace_history WHERE workspace_id=? GROUP BY dish_id HAVING COUNT(*) >= ?) AS eligible", (workspace_id, MIN_SERVICES)).fetchone()["count"]
        if not eligible:
            raise HTTPException(409, "At least one dish needs 56 recorded services before training")
        pending = conn.execute("SELECT 1 FROM model_jobs WHERE workspace_id=? AND status IN ('queued','running') LIMIT 1", (workspace_id,)).fetchone()
        if pending:
            raise HTTPException(409, "A model run is already queued or running")
        latest = conn.execute("SELECT created_at FROM model_jobs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 1", (workspace_id,)).fetchone()
        if latest and latest["created_at"] > now - 3600:
            raise HTTPException(429, "Wait an hour before starting another model run")
        job_id = str(uuid.uuid4())
        conn.execute("INSERT INTO model_jobs(id,workspace_id,status,created_at) VALUES (?,?,?,?)", (job_id, workspace_id, "queued", now))
    return {"job_id": job_id, "status": "queued"}

@app.post("/api/models/rollback")
def rollback_model(user: dict = Depends(require_csrf)):
    if user["role"] != "owner":
        raise HTTPException(403, "Only the workspace owner can revert a model")
    with db() as conn:
        conn.execute("UPDATE workspaces SET data_mode=data_mode WHERE id=?", (user["workspace_id"],))
        conn.execute("UPDATE model_jobs SET status='rejected',finished_at=?,reason='Owner reverted to the standard forecast' WHERE workspace_id=? AND status IN ('queued','running')", (int(time.time()), user["workspace_id"]))
        changed = conn.execute("UPDATE model_versions SET status='archived' WHERE workspace_id=? AND status='active'", (user["workspace_id"],))
    if changed.rowcount == 0:
        raise HTTPException(409, "No active model to revert")
    return {"ok": True}

def import_preview(csv_text: str, data_mode: str):
    dishes, rows, days = parse_sales_csv(csv_text)
    counts = {key: 0 for key in dishes}
    for row in rows:
        counts[row["dish_key"]] += 1
    dish_services = sorted(({"name": dishes[key]["name"], "services": count} for key, count in counts.items()), key=lambda item: (-item["services"], item["name"]))
    return {"dishes": len(dishes), "services": len(days), "rows": len(rows), "prepared_rows": sum(row["prep_known"] for row in rows), "dish_names": sorted(dish["name"] for dish in dishes.values()), "dish_costs": sorted(dishes.values(), key=lambda dish: dish["name"]), "dish_services": dish_services, "eligible_dishes": sum(item["services"] >= MIN_SERVICES for item in dish_services), "first_day": min(days).isoformat(), "last_day": max(days).isoformat(), "replaces": data_mode}

@app.post("/api/import/inspect")
def inspect_spreadsheet(payload: SpreadsheetInput, user: dict = Depends(require_csrf)):
    try:
        content = import_mapping.decode_file(payload.filename, payload.content_base64)
        details, fallback = import_mapping.describe(payload.filename, content)
        with db() as conn:
            saved = conn.execute("SELECT mapping_json FROM workspace_import_mappings WHERE workspace_id=? AND source_signature=?", (user["workspace_id"], details["signature"])).fetchone()
        mapping, source = fallback, "rules"
        candidate = json.loads(saved["mapping_json"]) if saved else import_mapping.agent_mapping(details, fallback) if payload.use_agent else None
        if candidate:
            try:
                import_mapping.validate_mapping(candidate, import_mapping.tables(payload.filename, content))
                mapping, source = candidate, "saved" if saved else "agent"
            except (ValueError, TypeError):
                pass
        return {**details, "mapping": mapping, "mapping_source": source}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error

@app.post("/api/import/normalize")
def normalize_spreadsheet(payload: MappedSpreadsheetInput, user: dict = Depends(current_user)):
    try:
        content = import_mapping.decode_file(payload.filename, payload.content_base64)
        csv_text = import_mapping.normalize(payload.filename, content, payload.mapping)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    preview = import_preview(csv_text, user["data_mode"])
    reader = csv.DictReader(io.StringIO(csv_text))
    return {"csv_text": csv_text, "preview": preview, "sample": [row for _, row in zip(range(5), reader)]}

@app.post("/api/import/menu/inspect")
def inspect_menu_spreadsheet(payload: SpreadsheetInput, user: dict = Depends(require_csrf)):
    try:
        content = import_mapping.decode_file(payload.filename, payload.content_base64)
        details, mapping = import_mapping.describe_menu(payload.filename, content)
        return {**details, "mapping": mapping}
    except ValueError as error:
        raise HTTPException(400, str(error)) from error

@app.post("/api/import/menu/normalize")
def normalize_menu_spreadsheet(payload: MappedMenuSpreadsheetInput, user: dict = Depends(current_user)):
    try:
        content = import_mapping.decode_file(payload.filename, payload.content_base64)
        menu = import_mapping.normalize_menu(payload.filename, content, payload.mapping)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"menu": menu, "items": len(menu)}

@app.post("/api/import/commit")
def commit_import(payload: SalesCsvInput, user: dict = Depends(require_csrf)):
    if user["role"] != "owner":
        raise HTTPException(403, "Only the workspace owner can import service history")
    dishes, rows, days = parse_sales_csv(payload.csv_text)
    if payload.train:
        missing = [dish["name"] for dish in dishes.values() if dish["id"] not in payload.menu_costs]
        if missing:
            raise HTTPException(400, "Menu costs are missing for: " + ", ".join(missing[:5]))
    default_cost_dishes = 0
    for dish in dishes.values():
        override = payload.menu_costs.get(dish["id"])
        if override:
            dish["ingredient_cost"] = round(override.ingredient_cost, 2)
            dish["price"] = round(override.price, 2)
        if dish["ingredient_cost"] is None or dish["price"] is None:
            # Keep a file-only import moving; the owner can replace these conservative placeholders in Menu costs.
            dish["ingredient_cost"] = 5.00
            dish["price"] = 15.00
            default_cost_dishes += 1
        if dish["ingredient_cost"] <= 0 or dish["price"] <= dish["ingredient_cost"]:
            raise HTTPException(400, f"Sale price must exceed ingredient cost for {dish['name']}")
    mapping_json = None
    if payload.source_mapping is not None or payload.source_signature is not None:
        if not payload.source_mapping or not payload.source_signature or not re.fullmatch(r"[0-9a-f]{64}", payload.source_signature):
            raise HTTPException(400, "Invalid saved spreadsheet mapping")
        mapping_json = json.dumps(payload.source_mapping, sort_keys=True, separators=(",", ":"))
        if len(mapping_json) > 10_000:
            raise HTTPException(400, "Spreadsheet mapping is too large")
    workspace_id = user["workspace_id"]
    training = {"status": "not_configured"}
    with db() as conn:
        # The worker takes the same row lock before promotion.
        conn.execute("UPDATE workspaces SET data_mode=data_mode WHERE id=?", (workspace_id,))
        conn.execute("UPDATE model_jobs SET status='rejected',finished_at=?,reason='Service history was replaced' WHERE workspace_id=? AND status IN ('queued','running')", (int(time.time()), workspace_id))
        conn.execute("UPDATE model_versions SET status='archived' WHERE workspace_id=? AND status='active'", (workspace_id,))
        conn.execute("DELETE FROM workspace_history WHERE workspace_id=?", (workspace_id,))
        conn.execute("DELETE FROM workspace_dishes WHERE workspace_id=?", (workspace_id,))
        for dish in dishes.values():
            matching = [row["sold"] for row in rows if row["dish_key"] == dish["name"].casefold()]
            baseline = round(sum(matching[-14:]) / max(1, len(matching[-14:])))
            conn.execute("INSERT INTO workspace_dishes VALUES (?,?,?,?,?,?,?,?,?)", (workspace_id, dish["id"], dish["name"], dish["category"], dish["price"], dish["ingredient_cost"], baseline, 0, "Imported from sales CSV"))
        conn.executemany("INSERT INTO workspace_history(workspace_id,day,dish_id,sold,prepared,leftover,covers,prep_known) VALUES (?,?,?,?,?,?,?,?)", [(workspace_id, row["day"], dishes[row["dish_key"]]["id"], row["sold"], row["prepared"], row["leftover"], row["covers"], row["prep_known"]) for row in rows])
        conn.execute("UPDATE workspaces SET data_mode='imported' WHERE id=?", (workspace_id,))
        eligible = sum(1 for dish in dishes.values() if sum(1 for row in rows if row["dish_key"] == dish["name"].casefold()) >= MIN_SERVICES)
        if payload.train and os.getenv("YLD_MODEL_WORKER_ENABLED") == "1" and eligible:
            job_id = str(uuid.uuid4())
            latest = conn.execute("SELECT MAX(created_at) AS created_at FROM model_jobs WHERE workspace_id=?", (workspace_id,)).fetchone()
            created_at = max(int(time.time()), (latest["created_at"] or 0) + 1)
            conn.execute("INSERT INTO model_jobs(id,workspace_id,status,created_at) VALUES (?,?,?,?)", (job_id, workspace_id, "queued", created_at))
            training = {"status": "queued", "job_id": job_id}
        elif payload.train and os.getenv("YLD_MODEL_WORKER_ENABLED") == "1":
            training = {"status": "not_ready", "required_services": MIN_SERVICES}
        if mapping_json:
            conn.execute("INSERT INTO workspace_import_mappings(workspace_id,source_signature,mapping_json,updated_at) VALUES (?,?,?,?) ON CONFLICT(workspace_id,source_signature) DO UPDATE SET mapping_json=excluded.mapping_json,updated_at=excluded.updated_at", (workspace_id, payload.source_signature, mapping_json, int(time.time())))
    return {"ok": True, "dishes": len(dishes), "services": len(days), "rows": len(rows), "prepared_rows": sum(row["prep_known"] for row in rows), "default_cost_dishes": default_cost_dishes, "training": training}

@app.get("/api/export/history")
def export_history(user: dict = Depends(current_user)):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(("date", "dish", "sold", "covers", "prepared", "ingredient_cost", "price", "category"))
    with db() as conn:
        rows = conn.execute("""SELECT h.day,d.name,h.sold,h.covers,h.prepared,h.prep_known,d.ingredient_cost,d.price,d.category
            FROM workspace_history h JOIN workspace_dishes d ON d.workspace_id=h.workspace_id AND d.id=h.dish_id
            WHERE h.workspace_id=? ORDER BY h.day,d.name""", (user["workspace_id"],))
        for row in rows:
            writer.writerow((row["day"], row["name"], row["sold"], row["covers"], row["prepared"] if row["prep_known"] else "", row["ingredient_cost"], row["price"], row["category"]))
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="yld-service-history.csv"'})

@app.patch("/api/dishes/{dish_id}")
def update_dish_costs(dish_id: str, payload: DishCostsInput, user: dict = Depends(require_csrf)):
    if payload.price <= payload.ingredient_cost:
        raise HTTPException(400, "Sale price must be higher than ingredient cost")
    with db() as conn:
        result = conn.execute(
            "UPDATE workspace_dishes SET ingredient_cost=?, price=? WHERE workspace_id=? AND id=?",
            (payload.ingredient_cost, payload.price, user["workspace_id"], dish_id),
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Dish not found")
    return {"ok": True}

@app.post("/api/actuals")
def save_actual(payload: ActualInput, user: dict = Depends(require_csrf)):
    if payload.day > local_today():
        raise HTTPException(400, "Service date cannot be in the future")
    if payload.sold > payload.prepared:
        raise HTTPException(400, "Sold cannot exceed prepared")
    with db() as conn:
        # Serialize history edits with model promotion and CSV replacement.
        conn.execute("UPDATE workspaces SET data_mode=data_mode WHERE id=?", (user["workspace_id"],))
        if not conn.execute("SELECT 1 FROM workspace_dishes WHERE workspace_id=? AND id=?", (user["workspace_id"], payload.dish_id)).fetchone():
            raise HTTPException(404, "Dish not found")
        previous = conn.execute("SELECT sold,prepared,covers,prep_known FROM workspace_history WHERE workspace_id=? AND day=? AND dish_id=?", (user["workspace_id"], payload.day.isoformat(), payload.dish_id)).fetchone()
        covers_changed = conn.execute("SELECT 1 FROM workspace_history WHERE workspace_id=? AND day=? AND covers<>? LIMIT 1", (user["workspace_id"], payload.day.isoformat(), payload.covers)).fetchone() is not None
        model_correction = covers_changed or (previous is not None and previous["sold"] != payload.sold)
        if model_correction or previous is None:
            conn.execute("UPDATE model_jobs SET status='rejected',finished_at=?,reason='Service history changed during training' WHERE workspace_id=? AND status IN ('queued','running')", (int(time.time()), user["workspace_id"]))
        if model_correction:
            conn.execute("UPDATE model_versions SET status='archived' WHERE workspace_id=? AND status='active'", (user["workspace_id"],))
        # Covers belong to the service, not an individual dish. Keep existing
        # rows for that day consistent when actual attendance is corrected.
        conn.execute("UPDATE workspace_history SET covers=? WHERE workspace_id=? AND day=?", (payload.covers, user["workspace_id"], payload.day.isoformat()))
        conn.execute("INSERT INTO workspace_history(workspace_id,day,dish_id,sold,prepared,leftover,covers,prep_known) VALUES (?,?,?,?,?,?,?,1) ON CONFLICT(workspace_id,day,dish_id) DO UPDATE SET sold=excluded.sold,prepared=excluded.prepared,leftover=excluded.leftover,covers=excluded.covers,prep_known=1", (user["workspace_id"], payload.day.isoformat(), payload.dish_id, payload.sold, payload.prepared, payload.prepared-payload.sold, payload.covers))
        summary = service_summary(conn, user["workspace_id"], payload.day)
    return {"ok": True, "summary": summary}

# One persistent FastAPI process can serve the built Vite app and API together.
DIST_PATH = Path(__file__).resolve().parents[1] / "dist"
if DIST_PATH.is_dir():
    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        requested = (DIST_PATH / full_path).resolve()
        if requested.is_file() and DIST_PATH.resolve() in requested.parents:
            return FileResponse(requested)
        return FileResponse(DIST_PATH / "index.html")
