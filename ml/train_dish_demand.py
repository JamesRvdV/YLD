"""Train next-service, per-dish portion forecasts on public restaurant sales."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path

import joblib
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

if __package__:
    from .cover_baseline import score
else:
    from cover_baseline import score


DATA_PATH = Path(__file__).parent / "data" / "restaurant_dish_sales.csv"
ARTIFACT_PATH = Path(__file__).parent / "dish_demand_model.joblib"
REPORT_PATH = Path(__file__).parent / "dish_demand_report.json"

def feature_names(dishes):
    return (
        *(f"dish_{dish}" for dish in dishes),
        *(f"weekday_{weekday}" for weekday in range(7)),
        "month_sin", "month_cos", "dish_last", "dish_recent_7_mean",
        "dish_recent_28_mean", "dish_same_weekday_4_mean",
        "total_last", "total_recent_7_mean", "total_recent_28_mean",
        "total_same_weekday_4_mean", "dish_share_recent_28",
    )


def load_sales(path: Path):
    by_day = {}
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if not {"date", "dish", "sold"}.issubset(reader.fieldnames or []):
            raise ValueError("Expected date, dish, sold columns")
        for row in reader:
            day = date.fromisoformat(row["date"])
            dish = row["dish"]
            sold = int(row["sold"])
            if not dish or sold < 0 or dish in by_day.setdefault(day, {}):
                raise ValueError(f"Invalid or duplicate sale for {dish} on {day}")
            by_day[day][dish] = sold
    days = sorted(by_day)
    if not days:
        raise ValueError("No sales records")
    dishes = sorted(by_day[days[0]])
    if len(days) < 60 or any(set(by_day[day]) != set(dishes) for day in days):
        raise ValueError("Need at least 60 complete service days for the same dishes")
    return days, by_day, dishes


def feature_row(target_day, dish, dishes, dish_recent, dish_same_weekday, total_recent, total_same_weekday):
    return (
        [float(dish == candidate) for candidate in dishes]
        + [float(target_day.weekday() == weekday) for weekday in range(7)]
        + [math.sin(2 * math.pi * target_day.month / 12),
           math.cos(2 * math.pi * target_day.month / 12),
           float(dish_recent[-1]), sum(dish_recent[-7:]) / 7,
           sum(dish_recent) / 28, dish_same_weekday,
           float(total_recent[-1]), sum(total_recent[-7:]) / 7,
           sum(total_recent) / 28, total_same_weekday,
           sum(dish_recent) / max(1, sum(total_recent))]
    )


def make_samples(days, by_day, dishes):
    totals = [sum(by_day[day].values()) for day in days]
    per_dish = {dish: [by_day[day][dish] for day in days] for dish in dishes}
    samples, targets, metadata, naive = [], [], [], []
    for index in range(28, len(days)):
        target_day = days[index]
        same_weekday = [earlier for earlier in range(index) if days[earlier].weekday() == target_day.weekday()][-4:]
        total_recent = totals[index - 28:index]
        total_same_weekday = sum(totals[earlier] for earlier in same_weekday) / len(same_weekday)
        for dish in dishes:
            history = per_dish[dish]
            recent = history[index - 28:index]
            weekday_mean = sum(history[earlier] for earlier in same_weekday) / len(same_weekday)
            sample = feature_row(target_day, dish, dishes, recent, weekday_mean, total_recent, total_same_weekday)
            samples.append(sample)
            targets.append(history[index])
            metadata.append((target_day, dish))
            naive.append(weekday_mean)
    return samples, targets, metadata, naive


def forecast(artifact: Path, history: Path, target_day: date):
    bundle = joblib.load(artifact)
    days, by_day, dishes = load_sales(history)
    if tuple(dishes) != tuple(bundle["dishes"]):
        raise ValueError("Dish set differs from the trained model")
    if target_day <= days[-1]:
        raise ValueError("Forecast date must follow the last observed service date")
    same_weekday = [day for day in days if day.weekday() == target_day.weekday()][-4:]
    if not same_weekday:
        raise ValueError("Need prior observations for the forecast weekday")
    total_recent = [sum(by_day[day].values()) for day in days[-28:]]
    total_weekday_mean = sum(sum(by_day[day].values()) for day in same_weekday) / len(same_weekday)
    rows = []
    for dish in dishes:
        dish_recent = [by_day[day][dish] for day in days[-28:]]
        weekday_mean = sum(by_day[day][dish] for day in same_weekday) / len(same_weekday)
        rows.append(feature_row(target_day, dish, dishes, dish_recent, weekday_mean, total_recent, total_weekday_mean))
    predictions = clipped(bundle["estimator"], rows)
    return {dish: round(value, 2) for dish, value in zip(dishes, predictions)}


def candidates():
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=100)),
        "extra_trees": ExtraTreesRegressor(
            n_estimators=300, max_depth=10, min_samples_leaf=5,
            max_features=0.85, n_jobs=1, random_state=42,
        ),
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            loss="poisson", max_iter=200, learning_rate=0.05,
            max_leaf_nodes=15, min_samples_leaf=20,
            l2_regularization=10, early_stopping=False, random_state=42,
        ),
    }


def clipped(model, samples):
    return [max(0.0, float(value)) for value in model.predict(samples)]


def train(data: Path, artifact: Path, report_path: Path):
    days, by_day, dishes = load_sales(data)
    samples, targets, metadata, naive = make_samples(days, by_day, dishes)
    validation = (int(len(days) * 0.7) - 28) * len(dishes)
    holdout = (int(len(days) * 0.8) - 28) * len(dishes)
    validation_scores = {}
    for name, model in candidates().items():
        model.fit(samples[:validation], targets[:validation])
        validation_scores[name] = score(targets[validation:holdout], clipped(model, samples[validation:holdout]))
    winner = min(validation_scores, key=lambda name: validation_scores[name]["mae"])
    evaluation_model = candidates()[winner]
    evaluation_model.fit(samples[:holdout], targets[:holdout])
    predictions = clipped(evaluation_model, samples[holdout:])
    actual = targets[holdout:]
    by_dish = {}
    for dish in dishes:
        indices = [index for index, (_, item) in enumerate(metadata[holdout:]) if item == dish]
        by_dish[dish] = score([actual[index] for index in indices], [predictions[index] for index in indices])
    report = {
        "target": "portions_sold_per_dish_per_service",
        "source": "https://data.mendeley.com/datasets/xv5kp6mxv7/1",
        "data_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
        "features": feature_names(dishes),
        "service_days": len(days), "dishes": dishes,
        "train_end": days[int(len(days) * 0.7) - 1].isoformat(),
        "validation_start": days[int(len(days) * 0.7)].isoformat(),
        "validation_end": days[int(len(days) * 0.8) - 1].isoformat(),
        "holdout_start": days[int(len(days) * 0.8)].isoformat(),
        "holdout_end": days[-1].isoformat(),
        "selection": "Lowest validation MAE",
        "validation_scores": validation_scores,
        "selected_model": winner,
        "holdout_scores": {
            winner: score(actual, predictions),
            "same_weekday_last_4": score(actual, naive[holdout:]),
        },
        "holdout_by_dish": by_dish,
        "one_step_ahead": True,
        "final_train_samples": len(samples),
    }
    final_model = candidates()[winner]
    final_model.fit(samples, targets)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"estimator": final_model, "features": feature_names(dishes), "dishes": dishes, "report": report}, artifact)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--artifact", type=Path, default=ARTIFACT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--predict-date", type=date.fromisoformat,
                        help="Forecast a future service date using --data as sales history")
    args = parser.parse_args()
    result = forecast(args.artifact, args.data, args.predict_date) if args.predict_date else train(args.data, args.artifact, args.report)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
