"""Fixed, auditable model family used by the isolated trainer and production API.

No pickle, Python source, imports, or expressions are accepted as model artifacts.
"""
from __future__ import annotations

import math
import json
from datetime import date
from pathlib import Path
from statistics import pstdev

from api.json_contract import validate as validate_json


WINDOWS = (28, 56, 112)
PENALTIES = (0.5, 2.0, 10.0, 50.0)
FEATURE_COUNT = 10
MAX_MODELS = 100
MIN_SERVICES = 56  # 28 initial fit + 14 agent validation + 14 untouched promotion test
SELECTION_SCHEMA = json.loads(Path(__file__).with_name("model_selection.schema.json").read_text())
ARTIFACT_SCHEMA = json.loads(Path(__file__).with_name("model_artifact.schema.json").read_text())


def exact_object(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"Expected exactly: {', '.join(fields)}")
    return value


def selection(value):
    validate_json(SELECTION_SCHEMA, value)
    exact_object(value, ("algorithm", "window", "penalty", "reason"))
    if value["algorithm"] not in ("ridge_weekday_v1", "ridge_decay_v1"):
        raise ValueError("Unsupported algorithm")
    if type(value["window"]) is not int or value["window"] not in WINDOWS:
        raise ValueError("Unsupported training window")
    if type(value["penalty"]) not in (int, float) or value["penalty"] not in PENALTIES:
        raise ValueError("Unsupported penalty")
    if not isinstance(value["reason"], str) or not 1 <= len(value["reason"]) <= 240:
        raise ValueError("Reason must be 1–240 characters")
    return value


def features(day: str, covers: int, trend: float):
    weekday = date.fromisoformat(day).weekday()
    return [1.0, covers / 75.0] + [float(weekday == index) for index in range(7)] + [trend]


def solve_ridge(samples, targets, penalty, weights=None):
    size = len(samples[0])
    matrix = [[0.0] * (size + 1) for _ in range(size)]
    for vector, target, weight in zip(samples, targets, weights or [1.0] * len(samples)):
        for i in range(size):
            matrix[i][-1] += weight * vector[i] * target
            for j in range(size):
                matrix[i][j] += weight * vector[i] * vector[j]
    for i in range(1, size):
        matrix[i][i] += penalty
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(matrix[row][col]))
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        scale = matrix[col][col]
        if abs(scale) < 1e-10:
            raise ValueError("Singular model fit")
        matrix[col] = [v / scale for v in matrix[col]]
        for row in range(size):
            if row == col:
                continue
            multiple = matrix[row][col]
            matrix[row] = [v - multiple * p for v, p in zip(matrix[row], matrix[col])]
    return [matrix[i][-1] for i in range(size)]


def cover_estimate(services, target_day: date):
    """Same past-only cover estimate used by live planning and model evaluation."""
    service_days = len(services)
    if service_days < 14:
        return None, service_days
    recent = services[-56:]
    samples, weights, outcomes = [], [], []
    for index, service in enumerate(recent):
        weekday = date.fromisoformat(service["day"]).weekday()
        samples.append([1.0] + [float(weekday == day) for day in range(7)] + [index / max(1, len(recent) - 1)])
        weights.append(math.exp((index - len(recent) + 1) / 28))
        outcomes.append(float(service["covers"]))
    coefficients = solve_ridge(samples, outcomes, 2.0, weights)
    target = [1.0] + [float(target_day.weekday() == day) for day in range(7)] + [1.0]
    estimate = round(sum(a * b for a, b in zip(coefficients, target)))
    return max(1, min(1000, estimate)), service_days


def services_from_dishes(dishes):
    """One cover observation per workspace service date, across all dishes."""
    by_day = {}
    for dish in dishes:
        for row in dish["rows"]:
            day, covers = row["day"], row["covers"]
            if day in by_day and by_day[day] != covers:
                raise ValueError("Inconsistent covers for a service date")
            by_day[day] = covers
    return [{"day": day, "covers": by_day[day]} for day in sorted(by_day)]


def fit(rows, spec):
    """Fit a dish with past-only numeric observations."""
    spec = selection(spec)
    recent = rows[-spec["window"]:]
    if len(recent) < 28:
        raise ValueError("At least 28 observations are required")
    samples = [features(row["day"], row["covers"], index / max(1, len(recent) - 1)) for index, row in enumerate(recent)]
    targets = [row["sold"] for row in recent]
    weights = [math.exp((index - len(recent) + 1) / 28) for index in range(len(recent))] if spec["algorithm"] == "ridge_decay_v1" else None
    coefficients = solve_ridge(samples, targets, spec["penalty"], weights)
    residuals = [target - sum(a * b for a, b in zip(coefficients, vector)) for target, vector in zip(targets, samples)]
    sigma = max(1.8, pstdev(residuals))
    return {"coefficients": [round(value, 8) for value in coefficients], "sigma": round(sigma, 8), "min_covers": min(row["covers"] for row in recent), "max_covers": max(row["covers"] for row in recent), "max_sold": max(targets)}


def validate_artifact(value, allowed_ids=None):
    validate_json(ARTIFACT_SCHEMA, value)
    exact_object(value, ("schema_version", "algorithm", "window", "penalty", "models"))
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported artifact schema")
    selection({"algorithm": value["algorithm"], "window": value["window"], "penalty": value["penalty"], "reason": "artifact"})
    models = value["models"]
    if not isinstance(models, list) or not 1 <= len(models) <= MAX_MODELS:
        raise ValueError("Invalid model count")
    ids = set()
    for model in models:
        exact_object(model, ("dish_id", "coefficients", "sigma", "min_covers", "max_covers", "max_sold"))
        dish_id = model["dish_id"]
        if not isinstance(dish_id, str) or not 1 <= len(dish_id) <= 64 or dish_id in ids:
            raise ValueError("Invalid or duplicate dish ID")
        if allowed_ids is not None and dish_id not in allowed_ids:
            raise ValueError("Artifact contains another workspace's dish")
        ids.add(dish_id)
        coefficients = model["coefficients"]
        if not isinstance(coefficients, list) or len(coefficients) != FEATURE_COUNT:
            raise ValueError("Invalid coefficient count")
        if any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 10000 for x in coefficients):
            raise ValueError("Invalid coefficient")
        sigma = model["sigma"]
        if type(sigma) not in (int, float) or not math.isfinite(sigma) or not 1.8 <= sigma <= 10000:
            raise ValueError("Invalid uncertainty")
        if any(type(model[field]) is not int for field in ("min_covers", "max_covers", "max_sold")):
            raise ValueError("Invalid training range")
        if not (1 <= model["min_covers"] <= model["max_covers"] <= 100000 and 0 <= model["max_sold"] <= 1000000):
            raise ValueError("Invalid training range")
    return value


def predict(model, day: str, covers: int, event_boost=0):
    # Future predictions sit one step after the final training observation.
    vector = features(day, covers, 1.0)
    mean = max(0.0, sum(a * b for a, b in zip(model["coefficients"], vector)))
    return mean * (1 + event_boost / 100), model["sigma"]


def supported(model, covers: int, mean: float):
    return model["min_covers"] * 0.5 <= covers <= model["max_covers"] * 1.5 and mean <= max(20, 2 * model["max_sold"])
