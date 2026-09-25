from __future__ import annotations

import math
import os
import random
import sqlite3
import hashlib
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from statistics import pstdev

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("YLD_DB_PATH", Path(__file__).parent / "yld.db"))
app = FastAPI(title="YLD Prep Planner API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS dishes (id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL, ingredient_cost REAL NOT NULL, baseline INTEGER NOT NULL, shortage_cost REAL NOT NULL, description TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS service_history (day TEXT NOT NULL, dish_id TEXT NOT NULL, sold INTEGER NOT NULL, prepared INTEGER NOT NULL, leftover INTEGER NOT NULL, covers INTEGER NOT NULL, PRIMARY KEY(day,dish_id));
        CREATE TABLE IF NOT EXISTS service_notes (day TEXT PRIMARY KEY, covers INTEGER NOT NULL, event_boost INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, name TEXT NOT NULL);
        """)
        conn.execute("INSERT OR IGNORE INTO users(email,password_hash,name) VALUES (?,?,?)", ("owner@yld.local", hashlib.sha256("YLDdemo!2026".encode()).hexdigest(), "YLD Owner"))
        if conn.execute("SELECT COUNT(*) FROM dishes").fetchone()[0] == 0:
            conn.executemany("INSERT INTO dishes VALUES (?,?,?,?,?,?,?,?)", ITEMS)
        if conn.execute("SELECT COUNT(*) FROM service_history").fetchone()[0] == 0:
            rng = random.Random(42)
            today = date.today()
            for offset in range(84, 0, -1):
                day = today - timedelta(days=offset)
                weekend = day.weekday() in (4, 5)
                covers = max(42, round((93 if weekend else 70) + rng.gauss(0, 9)))
                for idx, (item_id, _, _, _, _, baseline, _, _) in enumerate(ITEMS):
                    trend = 1 + (84-offset) * (0.0015 if idx in (1, 3) else -0.0006)
                    demand = max(0, round(baseline * covers / 75 * trend + rng.gauss(0, 2.5)))
                    usual_prep = max(0, round(baseline * (1.22 if weekend else 1.05) + rng.gauss(0, 2)))
                    sold = min(demand, usual_prep)
                    conn.execute("INSERT INTO service_history VALUES (?,?,?,?,?,?)", (day.isoformat(), item_id, sold, usual_prep, usual_prep-sold, covers))

init_db()

def history(conn, dish_id: str):
    return [dict(r) for r in conn.execute("SELECT * FROM service_history WHERE dish_id=? ORDER BY day", (dish_id,))]

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

def forecast_covers(conn, target_day):
    """Estimate covers from completed services once two weeks of history exist."""
    services = [dict(row) for row in conn.execute(
        "SELECT day, ROUND(AVG(covers)) AS covers FROM service_history WHERE day < ? GROUP BY day ORDER BY day",
        (target_day.isoformat(),),
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
        for idx in range(max(28, len(rows)-28), len(rows)):
            actual = rows[idx]
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
    return {"days": int(days), "usual_waste": round(totals["usual_waste"]), "model_waste": round(totals["model_waste"]), "difference": round(totals["usual_waste"]-totals["model_waste"]), "observed_missed": totals["observed_missed"]}

def build_plan(covers: int | None, event_boost: int, waste_weight: float):
    tomorrow = date.today() + timedelta(days=1)
    with db() as conn:
        estimated_covers, service_days = forecast_covers(conn, tomorrow)
        if covers is None and estimated_covers is None:
            raise HTTPException(409, {"code": "covers_needed", "service_days": service_days, "required_days": 14})
        cover_source = "forecast" if covers is None else "manual"
        covers = estimated_covers if covers is None else covers
        dishes = [dict(r) for r in conn.execute("SELECT * FROM dishes")]
        rows = []
        for dish in dishes:
            h = history(conn, dish["id"])
            mu, sigma = forecast(h, covers, tomorrow, event_boost)
            lost_sale_cost = dish["price"] - dish["ingredient_cost"] + dish["shortage_cost"]
            _, qty, expected_leftover, expected_missed = optimize(mu, sigma, dish["ingredient_cost"], lost_sale_cost, waste_weight)
            previous = h[-1]["prepared"] if h else dish["baseline"]
            rows.append({**dish, "forecast": round(mu, 1), "confidence_low": max(0, round(mu-1.28*sigma)), "confidence_high": round(mu+1.28*sigma), "prep": qty, "previous_prep": previous, "delta": qty-previous, "expected_leftover": round(expected_leftover, 1), "expected_missed": round(expected_missed, 1), "history": h})
        baseline_waste = sum(sum(r["leftover"] * d["ingredient_cost"] for r in d["history"][-28:]) for d in rows)
        baseline_days = min(28, len(rows[0]["history"])) if rows else 1
        expected_waste = sum(d["expected_leftover"] * d["ingredient_cost"] for d in rows)
        baseline_daily = baseline_waste / max(1, baseline_days)
        total_units = sum(d["prep"] for d in rows)
        trend = []
        completed_days = sorted({r["day"] for dish in rows for r in dish["history"] if r["day"] < date.today().isoformat()})[-14:]
        for day in completed_days:
            daily = [r for d in rows for r in d["history"] if r["day"] == day]
            trend.append({"day": day, "label": date.fromisoformat(day).strftime("%d %b"), "waste": round(sum(r["leftover"] * next(x["ingredient_cost"] for x in rows if x["id"] == r["dish_id"]) for r in daily)), "prepared": sum(r["prepared"] for r in daily)})
        return {"date": tomorrow.isoformat(), "covers": covers, "cover_source": cover_source, "cover_history_days": service_days, "forecast_covers": estimated_covers, "event_boost": event_boost, "waste_weight": waste_weight, "dishes": [{k:v for k,v in d.items() if k != "history"} for d in rows], "summary": {"prep_units": total_units, "expected_waste": round(expected_waste), "usual_waste": round(baseline_daily), "waste_reduction": round(max(0, (baseline_daily-expected_waste)/max(1, baseline_daily)*100)), "at_risk": round(sum(d["expected_missed"] for d in rows), 1)}, "trend": trend, "backtest": backtest(rows, waste_weight)}

class PlanInput(BaseModel):
    covers: int | None = Field(None, ge=1, le=1000)
    event_boost: int = Field(0, ge=-50, le=100)
    waste_weight: float = Field(1.0, ge=0.2, le=3.0)

class ActualInput(BaseModel):
    day: date
    covers: int = Field(ge=1, le=1000)
    dish_id: str
    prepared: int = Field(ge=0)
    sold: int = Field(ge=0)

class LoginInput(BaseModel):
    email: str
    password: str

class DishCostsInput(BaseModel):
    ingredient_cost: float = Field(gt=0, le=10000)
    price: float = Field(gt=0, le=10000)

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/auth/login")
def login(payload: LoginInput):
    password_hash = hashlib.sha256(payload.password.encode()).hexdigest()
    with db() as conn:
        user = conn.execute("SELECT email,name FROM users WHERE email=? AND password_hash=?", (payload.email.lower().strip(), password_hash)).fetchone()
    if not user:
        raise HTTPException(401, "Incorrect email or password")
    return {"ok": True, "user": dict(user)}

@app.post("/api/plan")
def plan(payload: PlanInput):
    return build_plan(payload.covers, payload.event_boost, payload.waste_weight)

@app.patch("/api/dishes/{dish_id}")
def update_dish_costs(dish_id: str, payload: DishCostsInput):
    if payload.price <= payload.ingredient_cost:
        raise HTTPException(400, "Sale price must be higher than ingredient cost")
    with db() as conn:
        result = conn.execute(
            "UPDATE dishes SET ingredient_cost=?, price=? WHERE id=?",
            (payload.ingredient_cost, payload.price, dish_id),
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Dish not found")
    return {"ok": True}

@app.post("/api/actuals")
def save_actual(payload: ActualInput):
    if payload.day > date.today():
        raise HTTPException(400, "Service date cannot be in the future")
    if payload.sold > payload.prepared:
        raise HTTPException(400, "Sold cannot exceed prepared")
    with db() as conn:
        if not conn.execute("SELECT 1 FROM dishes WHERE id=?", (payload.dish_id,)).fetchone():
            raise HTTPException(404, "Dish not found")
        conn.execute("INSERT INTO service_history(day,dish_id,sold,prepared,leftover,covers) VALUES (?,?,?,?,?,?) ON CONFLICT(day,dish_id) DO UPDATE SET sold=excluded.sold,prepared=excluded.prepared,leftover=excluded.leftover,covers=excluded.covers", (payload.day.isoformat(), payload.dish_id, payload.sold, payload.prepared, payload.prepared-payload.sold, payload.covers))
    return {"ok": True}
