from __future__ import annotations

import math
import csv
import io
import os
import random
import sqlite3
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
from statistics import pstdev
from typing import Optional
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("YLD_DB_PATH", Path(__file__).parent / "yld.db"))
PUBLIC_URL = os.getenv("YLD_PUBLIC_URL", "http://127.0.0.1:5173").rstrip("/")
SESSION_SECONDS = 7 * 24 * 60 * 60
LINK_SECONDS = 48 * 60 * 60
COOKIE_NAME = "yld_session"
BUSINESS_TZ = ZoneInfo("Pacific/Auckland")
if os.getenv("YLD_ENV") == "production":
    if not PUBLIC_URL.startswith("https://") or not DB_PATH.is_absolute() or not os.getenv("RESEND_API_KEY") or not os.getenv("YLD_EMAIL_FROM"):
        raise RuntimeError("Production requires HTTPS YLD_PUBLIC_URL, absolute YLD_DB_PATH, RESEND_API_KEY and YLD_EMAIL_FROM")
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

ITEMS = [
    ("short-rib", "Braised short rib", "MAINS", 32, 12.8, 18, 3.5, "Slow braised, red wine jus"),
    ("mushroom", "Wild mushroom pasta", "MAINS", 27, 8.4, 24, 4.2, "Brown butter, parmesan"),
    ("chicken", "Roast chicken", "MAINS", 29, 10.2, 21, 3.8, "Lemon, pan gravy"),
    ("burrata", "Burrata & tomatoes", "STARTERS", 19, 6.5, 17, 3.0, "Heirloom tomato, basil"),
    ("tart", "Dark chocolate tart", "DESSERT", 15, 4.1, 15, 2.4, "Crème fraîche, sea salt"),
]

@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id), email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, role TEXT NOT NULL, activated_at INTEGER);
        CREATE TABLE IF NOT EXISTS workspace_dishes (workspace_id TEXT NOT NULL REFERENCES workspaces(id), id TEXT NOT NULL, name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL, ingredient_cost REAL NOT NULL, baseline INTEGER NOT NULL, shortage_cost REAL NOT NULL, description TEXT NOT NULL, PRIMARY KEY(workspace_id,id));
        CREATE TABLE IF NOT EXISTS workspace_history (workspace_id TEXT NOT NULL REFERENCES workspaces(id), day TEXT NOT NULL, dish_id TEXT NOT NULL, sold INTEGER NOT NULL, prepared INTEGER NOT NULL, leftover INTEGER NOT NULL, covers INTEGER NOT NULL, PRIMARY KEY(workspace_id,day,dish_id), FOREIGN KEY(workspace_id,dish_id) REFERENCES workspace_dishes(workspace_id,id));
        CREATE TABLE IF NOT EXISTS auth_links (token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), kind TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER, created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS auth_links_account ON auth_links(account_id,created_at);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS sessions_account ON sessions(account_id);
        """)
        if "data_mode" not in {row[1] for row in conn.execute("PRAGMA table_info(workspaces)")}:
            conn.execute("ALTER TABLE workspaces ADD COLUMN data_mode TEXT NOT NULL DEFAULT 'sample'")
        if "prep_known" not in {row[1] for row in conn.execute("PRAGMA table_info(workspace_history)")}:
            conn.execute("ALTER TABLE workspace_history ADD COLUMN prep_known INTEGER NOT NULL DEFAULT 1")

def seed_sample_data(conn, workspace_id: str):
    """An isolated, repeatable fictional kitchen for each invited workspace."""
    conn.executemany("INSERT INTO workspace_dishes VALUES (?,?,?,?,?,?,?,?,?)", [(workspace_id, *item) for item in ITEMS])
    rng = random.Random(42)
    today = local_today()
    for offset in range(84, 0, -1):
        day = today - timedelta(days=offset)
        weekend = day.weekday() in (4, 5)
        covers = max(42, round((93 if weekend else 70) + rng.gauss(0, 9)))
        for idx, (item_id, _, _, _, _, baseline, _, _) in enumerate(ITEMS):
            trend = 1 + (84-offset) * (0.0015 if idx in (1, 3) else -0.0006)
            demand = max(0, round(baseline * covers / 75 * trend + rng.gauss(0, 2.5)))
            usual_prep = max(0, round(baseline * (1.22 if weekend else 1.05) + rng.gauss(0, 2)))
            sold = min(demand, usual_prep)
            conn.execute("INSERT INTO workspace_history(workspace_id,day,dish_id,sold,prepared,leftover,covers) VALUES (?,?,?,?,?,?,?)", (workspace_id, day.isoformat(), item_id, sold, usual_prep, usual_prep-sold, covers))

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
        missing = [name for name in ("day", "dish", "sold", "covers", "ingredient_cost", "price") if not columns[name]]
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
            if price <= ingredient_cost:
                raise ValueError(f"Row {line_number}: price must exceed ingredient_cost")
            category = cell("category") or "MENU"
            if len(category) > 60:
                raise ValueError(f"Row {line_number}: category is too long")
            if (day, dish_key) in seen:
                raise ValueError(f"Row {line_number}: duplicate dish and date")
            seen.add((day, dish_key))
            if day in daily_covers and daily_covers[day] != covers:
                raise ValueError(f"Row {line_number}: covers must match for all dishes on a date")
            daily_covers[day] = covers
            if dish_key in dishes and (dishes[dish_key]["ingredient_cost"], dishes[dish_key]["price"]) != (ingredient_cost, price):
                raise ValueError(f"Row {line_number}: costs for {name} differ across rows")
            dishes[dish_key] = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, dish_key)), "name": name, "category": category.upper(), "ingredient_cost": ingredient_cost, "price": price}
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
    action = "Accept your invitation" if kind == "invite" else "Sign in"
    minutes = "48 hours" if kind == "invite" else "15 minutes"
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
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Idempotency-Key": link_id},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as result:
            if result.status not in (200, 201):
                raise RuntimeError("Resend did not accept the email")
    except (HTTPError, URLError) as error:
        raise RuntimeError("Resend could not send the email; check the sender domain and API key") from error

def send_signin_email(email: str, workspace_name: str, link: str):
    try:
        send_link_email(email, workspace_name, link, "login", str(uuid.uuid4()))
    except RuntimeError as error:
        logger.error("Sign-in email delivery failed: %s", error)

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
                conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES (?,?,?)", (workspace_id, workspace_name, now))
                seed_sample_data(conn, workspace_id)
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
            conn.execute("INSERT INTO accounts VALUES (?,?,?,?,?,NULL)", (account_id, workspace_id, email, email.split('@')[0], role))
        conn.execute("INSERT INTO auth_links VALUES (?,?,?,?,NULL,?)", (token_hash(token), account_id, "invite", now + LINK_SECONDS, now))
    link = invite_url(token)
    if send:
        send_link_email(email, workspace_name, link, "invite", link_id)
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
    return {key: user[key] for key in ("id", "email", "name", "role", "workspace_id", "workspace_name", "csrf_token", "data_mode")}

def history(conn, workspace_id: str, dish_id: str):
    return [dict(r) for r in conn.execute("SELECT * FROM workspace_history WHERE workspace_id=? AND dish_id=? ORDER BY day", (workspace_id, dish_id))]

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
    service_days = len(services)
    if service_days < 14:
        return None, service_days
    recent = services[-56:]
    features, weights, outcomes = [], [], []
    for idx, service in enumerate(recent):
        weekday = date.fromisoformat(service["day"]).weekday()
        features.append([1.0] + [float(weekday == day) for day in range(7)] + [idx / max(1, len(recent)-1)])
        weights.append(math.exp((idx - len(recent) + 1) / 28))
        outcomes.append(service["covers"])
    coefficients = solve_ridge(features, outcomes, weights)
    target = [1.0] + [float(target_day.weekday() == day) for day in range(7)] + [1.0]
    estimate = round(sum(weight * value for weight, value in zip(coefficients, target)))
    return max(1, min(1000, estimate)), service_days

def normal_cdf(x):
    return (1 + math.erf(x / math.sqrt(2))) / 2

def normal_pdf(x):
    return math.exp(-x*x/2) / math.sqrt(2*math.pi)

def optimize(mu, sigma, ingredient_cost, shortage_cost, waste_weight):
    # Expected overage and underage for a normally distributed demand estimate.
    best = None
    for qty in range(max(0, math.floor(mu - 4*sigma)), math.ceil(mu + 4*sigma) + 1):
        z = (qty-mu)/sigma
        over = sigma * (normal_pdf(z) + z*normal_cdf(z))
        under = sigma * (normal_pdf(z) - z*(1-normal_cdf(z)))
        cost = over * ingredient_cost * waste_weight + under * shortage_cost
        if best is None or cost < best[0]:
            best = (cost, qty, over, under)
    return best

def backtest(dishes, waste_weight):
    """Walk forward over held-out services using only earlier observations."""
    totals = {"usual_waste": 0.0, "model_waste": 0.0, "observed_missed": 0, "services": 0}
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
    days = totals["services"] / max(1, len(dishes))
    return {"days": int(days), "available": totals["services"] > 0, "usual_waste": round(totals["usual_waste"]) if totals["services"] else None, "model_waste": round(totals["model_waste"]) if totals["services"] else None, "difference": round(totals["usual_waste"]-totals["model_waste"]) if totals["services"] else None, "observed_missed": totals["observed_missed"] if totals["services"] else None}

def build_plan(workspace_id: str, covers: Optional[int], event_boost: int, waste_weight: float):
    tomorrow = local_today() + timedelta(days=1)
    with db() as conn:
        estimated_covers, service_days = forecast_covers(conn, workspace_id, tomorrow)
        if covers is None and estimated_covers is None:
            raise HTTPException(409, {"code": "covers_needed", "service_days": service_days, "required_days": 14})
        cover_source = "forecast" if covers is None else "manual"
        covers = estimated_covers if covers is None else covers
        dishes = [dict(r) for r in conn.execute("SELECT * FROM workspace_dishes WHERE workspace_id=?", (workspace_id,))]
        rows = []
        for dish in dishes:
            h = history(conn, workspace_id, dish["id"])
            mu, sigma = forecast(h, covers, tomorrow, event_boost)
            lost_sale_cost = dish["price"] - dish["ingredient_cost"] + dish["shortage_cost"]
            _, qty, expected_leftover, expected_missed = optimize(mu, sigma, dish["ingredient_cost"], lost_sale_cost, waste_weight)
            previous = h[-1]["prepared"] if h else dish["baseline"]
            rows.append({**dish, "forecast": round(mu, 1), "confidence_low": max(0, round(mu-1.28*sigma)), "confidence_high": round(mu+1.28*sigma), "prep": qty, "previous_prep": previous, "delta": qty-previous, "expected_leftover": round(expected_leftover, 1), "expected_missed": round(expected_missed, 1), "history": h})
        baseline_waste = sum(sum(r["leftover"] * d["ingredient_cost"] for r in d["history"][-28:] if r["prep_known"]) for d in rows)
        known_days = {r["day"] for d in rows for r in d["history"][-28:] if r["prep_known"]}
        expected_waste = sum(d["expected_leftover"] * d["ingredient_cost"] for d in rows)
        baseline_daily = baseline_waste / len(known_days) if known_days else None
        total_units = sum(d["prep"] for d in rows)
        trend = []
        completed_days = sorted({r["day"] for dish in rows for r in dish["history"] if r["day"] < local_today().isoformat()})[-14:]
        for day in completed_days:
            daily = [r for d in rows for r in d["history"] if r["day"] == day]
            known = [r for r in daily if r["prep_known"]]
            trend.append({"day": day, "label": date.fromisoformat(day).strftime("%d %b"), "waste": round(sum(r["leftover"] * next(x["ingredient_cost"] for x in rows if x["id"] == r["dish_id"]) for r in known)) if known else None, "prepared": sum(r["prepared"] for r in known) if known else None})
        return {"date": tomorrow.isoformat(), "covers": covers, "cover_source": cover_source, "cover_history_days": service_days, "forecast_covers": estimated_covers, "event_boost": event_boost, "waste_weight": waste_weight, "dishes": [{k:v for k,v in d.items() if k != "history"} for d in rows], "summary": {"prep_units": total_units, "expected_waste": round(expected_waste), "usual_waste": round(baseline_daily) if baseline_daily is not None else None, "waste_reduction": round(max(0, (baseline_daily-expected_waste)/max(1, baseline_daily)*100)) if baseline_daily is not None else None, "at_risk": round(sum(d["expected_missed"] for d in rows), 1)}, "trend": trend, "backtest": backtest(rows, waste_weight)}

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

class RedeemInput(BaseModel):
    token: str = Field(min_length=20, max_length=256)

class DishCostsInput(BaseModel):
    ingredient_cost: float = Field(gt=0, le=10000)
    price: float = Field(gt=0, le=10000)

class SalesCsvInput(BaseModel):
    csv_text: str = Field(min_length=1, max_length=2_000_000)

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return {"user": public_user(user)}

@app.post("/api/auth/request-link")
def request_link(payload: EmailInput, background_tasks: BackgroundTasks):
    try:
        email = clean_email(payload.email)
    except ValueError:
        raise HTTPException(422, "Enter a valid email address")
    if not os.getenv("RESEND_API_KEY") or not os.getenv("YLD_EMAIL_FROM"):
        raise HTTPException(503, "Email sign-in is not configured")
    now = int(time.time())
    with db() as conn:
        account = conn.execute("SELECT a.id,w.name AS workspace_name FROM accounts a JOIN workspaces w ON w.id=a.workspace_id WHERE a.email=? AND a.activated_at IS NOT NULL", (email,)).fetchone()
        if account:
            recent = conn.execute("SELECT COUNT(*) FROM auth_links WHERE account_id=? AND created_at>?", (account["id"], now - 3600)).fetchone()[0]
            if recent < 3:
                token = secrets.token_urlsafe(32)
                conn.execute("INSERT INTO auth_links VALUES (?,?,?,?,NULL,?)", (token_hash(token), account["id"], "login", now + 15 * 60, now))
                link = invite_url(token)
            else:
                link = None
        else:
            link = None
    if account and link:
        background_tasks.add_task(send_signin_email, email, account["workspace_name"], link)
    return {"ok": True, "message": "If this address has access, a sign-in link is on its way."}

@app.post("/api/auth/redeem")
def redeem(payload: RedeemInput, response: Response):
    now = int(time.time())
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    with db() as conn:
        link = conn.execute("SELECT account_id FROM auth_links WHERE token_hash=? AND used_at IS NULL AND expires_at>?", (token_hash(payload.token), now)).fetchone()
        if not link:
            raise HTTPException(400, "This link has expired or has already been used")
        claimed = conn.execute("UPDATE auth_links SET used_at=? WHERE token_hash=? AND used_at IS NULL", (now, token_hash(payload.token)))
        if claimed.rowcount != 1:
            raise HTTPException(400, "This link has already been used")
        conn.execute("UPDATE accounts SET activated_at=COALESCE(activated_at,?) WHERE id=?", (now, link["account_id"]))
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

@app.post("/api/import/preview")
def preview_import(payload: SalesCsvInput, user: dict = Depends(current_user)):
    dishes, rows, days = parse_sales_csv(payload.csv_text)
    return {"dishes": len(dishes), "services": len(days), "rows": len(rows), "prepared_rows": sum(row["prep_known"] for row in rows), "dish_names": sorted(dish["name"] for dish in dishes.values()), "first_day": min(days).isoformat(), "last_day": max(days).isoformat(), "replaces": user["data_mode"]}

@app.post("/api/import/commit")
def commit_import(payload: SalesCsvInput, user: dict = Depends(require_csrf)):
    if user["role"] != "owner":
        raise HTTPException(403, "Only the workspace owner can import service history")
    dishes, rows, days = parse_sales_csv(payload.csv_text)
    workspace_id = user["workspace_id"]
    with db() as conn:
        conn.execute("DELETE FROM workspace_history WHERE workspace_id=?", (workspace_id,))
        conn.execute("DELETE FROM workspace_dishes WHERE workspace_id=?", (workspace_id,))
        for dish in dishes.values():
            matching = [row["sold"] for row in rows if row["dish_key"] == dish["name"].casefold()]
            baseline = round(sum(matching[-14:]) / max(1, len(matching[-14:])))
            conn.execute("INSERT INTO workspace_dishes VALUES (?,?,?,?,?,?,?,?,?)", (workspace_id, dish["id"], dish["name"], dish["category"], dish["price"], dish["ingredient_cost"], baseline, 0, "Imported from sales CSV"))
        conn.executemany("INSERT INTO workspace_history(workspace_id,day,dish_id,sold,prepared,leftover,covers,prep_known) VALUES (?,?,?,?,?,?,?,?)", [(workspace_id, row["day"], dishes[row["dish_key"]]["id"], row["sold"], row["prepared"], row["leftover"], row["covers"], row["prep_known"]) for row in rows])
        conn.execute("UPDATE workspaces SET data_mode='imported' WHERE id=?", (workspace_id,))
    return {"ok": True, "dishes": len(dishes), "services": len(days), "rows": len(rows), "prepared_rows": sum(row["prep_known"] for row in rows)}

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
        if not conn.execute("SELECT 1 FROM workspace_dishes WHERE workspace_id=? AND id=?", (user["workspace_id"], payload.dish_id)).fetchone():
            raise HTTPException(404, "Dish not found")
        conn.execute("INSERT INTO workspace_history(workspace_id,day,dish_id,sold,prepared,leftover,covers,prep_known) VALUES (?,?,?,?,?,?,?,1) ON CONFLICT(workspace_id,day,dish_id) DO UPDATE SET sold=excluded.sold,prepared=excluded.prepared,leftover=excluded.leftover,covers=excluded.covers,prep_known=1", (user["workspace_id"], payload.day.isoformat(), payload.dish_id, payload.sold, payload.prepared, payload.prepared-payload.sold, payload.covers))
    return {"ok": True}

@app.post("/api/demo/reset")
def reset_demo(user: dict = Depends(require_csrf)):
    if user["role"] != "owner":
        raise HTTPException(403, "Only the workspace owner can reset sample data")
    with db() as conn:
        conn.execute("DELETE FROM workspace_history WHERE workspace_id=?", (user["workspace_id"],))
        conn.execute("DELETE FROM workspace_dishes WHERE workspace_id=?", (user["workspace_id"],))
        seed_sample_data(conn, user["workspace_id"])
        conn.execute("UPDATE workspaces SET data_mode='sample' WHERE id=?", (user["workspace_id"],))
    return {"ok": True}

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
