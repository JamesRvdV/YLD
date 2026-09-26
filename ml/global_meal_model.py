"""Measure whether a pooled meal-demand model transfers to unseen centres and meals.

Input is the Genpact Food Demand Forecasting train.csv. No series identifier or
future order count is used as a model feature. Prior sales may be used for a
held-out series, as they would be in a new venue with its own sales history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


FEATURES = ["lag_1", "lag_2", "lag_4", "lag_8", "mean_4", "mean_12", "std_12", "week_gap"]
REQUIRED = {"week", "center_id", "meal_id", "num_orders"}


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    if set(frame) != REQUIRED or frame.isna().any().any():
        raise ValueError("Expected complete week, center_id, meal_id, num_orders columns")
    if (frame["num_orders"] < 0).any() or frame.duplicated(["week", "center_id", "meal_id"]).any():
        raise ValueError("Orders must be nonnegative and centre/meal/week keys unique")
    frame = frame.sort_values(["center_id", "meal_id", "week"]).reset_index(drop=True)
    group = frame.groupby(["center_id", "meal_id"], sort=False)["num_orders"]
    for lag in (1, 2, 4, 8):
        frame[f"lag_{lag}"] = group.shift(lag)
    for span in (4, 12):
        frame[f"mean_{span}"] = group.transform(lambda series: series.shift(1).rolling(span, min_periods=span).mean())
    frame["std_12"] = group.transform(lambda series: series.shift(1).rolling(12, min_periods=12).std())
    frame["week_gap"] = frame["week"] - frame.groupby(["center_id", "meal_id"], sort=False)["week"].shift(1)
    return frame.dropna(subset=FEATURES).reset_index(drop=True)


def load_frame(path: Path) -> pd.DataFrame:
    return add_features(pd.read_csv(path, usecols=lambda column: column in REQUIRED))


def forecast(artifact: Path, history: Path, target_week: int) -> dict:
    frame = pd.read_csv(history, usecols=lambda column: column in REQUIRED)
    if set(frame) != REQUIRED or frame.empty or frame[["center_id", "meal_id"]].drop_duplicates().shape[0] != 1:
        raise ValueError("Forecast history must have one centre/meal series with all required columns")
    if target_week <= int(frame["week"].max()):
        raise ValueError("Forecast week must follow the last observed week")
    future = frame.iloc[[-1]].copy()
    future["week"] = target_week
    future["num_orders"] = 0  # Placeholder; all target-week features are shifted past values.
    sample = add_features(pd.concat([frame, future], ignore_index=True))
    row = sample.iloc[[-1]]
    if int(row["week"].iloc[0]) != target_week:
        raise ValueError("At least 12 prior observations are needed")
    bundle = joblib.load(artifact)
    estimate = max(0, float(bundle["estimator"].predict(row[bundle["features"]])[0]))
    return {
        "week": target_week,
        "center_id": int(row["center_id"].iloc[0]),
        "meal_id": int(row["meal_id"].iloc[0]),
        "expected_orders": round(estimate, 2),
        "recent_4_expected_orders": round(float(row["mean_4"].iloc[0]), 2),
    }


def metrics(frame: pd.DataFrame, predictions: np.ndarray) -> dict:
    actual = frame["num_orders"].to_numpy(dtype=float)
    naive = frame["mean_4"].to_numpy(dtype=float)
    error = np.abs(actual - predictions)
    naive_error = np.abs(actual - naive)
    by_series = frame[["center_id", "meal_id"]].copy()
    by_series["model_error"] = error
    by_series["recent_4_error"] = naive_error
    by_series = by_series.groupby(["center_id", "meal_id"], sort=False)[["model_error", "recent_4_error"]].mean()
    return {
        "rows": len(frame),
        "centres": int(frame["center_id"].nunique()),
        "meals": int(frame["meal_id"].nunique()),
        "model_mae": round(float(error.mean()), 2),
        "recent_4_mae": round(float(naive_error.mean()), 2),
        "last_week_mae": round(float(np.abs(actual - frame["lag_1"].to_numpy()).mean()), 2),
        "recent_12_mae": round(float(np.abs(actual - frame["mean_12"].to_numpy()).mean()), 2),
        "four_weeks_ago_mae": round(float(np.abs(actual - frame["lag_4"].to_numpy()).mean()), 2),
        "model_wape": round(float(error.sum() / actual.sum()), 4),
        "recent_4_wape": round(float(naive_error.sum() / actual.sum()), 4),
        "series_beating_recent_4_fraction": round(float((by_series["model_error"] < by_series["recent_4_error"]).mean()), 3),
    }


def run(data: Path, artifact: Path, report_path: Path) -> dict:
    frame = load_frame(data)
    centres = np.sort(frame["center_id"].unique())
    meals = np.sort(frame["meal_id"].unique())
    rng = np.random.default_rng(42)
    held_centres = np.sort(rng.choice(centres, size=max(1, round(len(centres) * 0.2)), replace=False))
    held_meals = np.sort(rng.choice(meals, size=max(1, round(len(meals) * 0.2)), replace=False))
    center_holdout = frame["center_id"].isin(held_centres)
    meal_holdout = frame["meal_id"].isin(held_meals)
    familiar = ~center_holdout & ~meal_holdout
    train = frame[familiar & (frame["week"] <= 116)]
    validation = frame[familiar & frame["week"].between(117, 129)]
    if train.empty or validation.empty:
        raise ValueError("Insufficient observations for training and validation")
    candidates = {
        "poisson_80": HistGradientBoostingRegressor(loss="poisson", max_iter=80, max_leaf_nodes=31, min_samples_leaf=100, l2_regularization=10, random_state=42),
        "poisson_200": HistGradientBoostingRegressor(loss="poisson", max_iter=200, max_leaf_nodes=31, min_samples_leaf=100, l2_regularization=10, random_state=42),
    }
    validation_scores = {}
    validation_mae = {}
    for name, candidate in candidates.items():
        candidate.fit(train[FEATURES], train["num_orders"])
        predictions = np.maximum(0, candidate.predict(validation[FEATURES]))
        validation_scores[name] = metrics(validation, predictions)
        validation_mae[name] = float(np.abs(validation["num_orders"].to_numpy() - predictions).mean())
    winner = min(validation_mae, key=validation_mae.get)
    model = candidates[winner]
    evaluation = frame[familiar & (frame["week"] <= 129)]
    model.fit(evaluation[FEATURES], evaluation["num_orders"])
    test_week = frame["week"].between(130, 145)
    cohorts = {
        "seen_centres_seen_meals": test_week & familiar,
        "unseen_centres_seen_meals": test_week & center_holdout & ~meal_holdout,
        "seen_centres_unseen_meals": test_week & ~center_holdout & meal_holdout,
        "unseen_centres_unseen_meals": test_week & center_holdout & meal_holdout,
    }
    test_scores = {}
    for name, mask in cohorts.items():
        held = frame[mask]
        if held.empty:
            raise ValueError(f"Empty test cohort: {name}")
        test_scores[name] = metrics(held, np.maximum(0, model.predict(held[FEATURES])))
    report = {
        "source": "Genpact Food Demand Forecasting / Analytics Vidhya; public copy: https://github.com/Shivansh-Commits/Food-Demand-Forecasting-DATA-SCIENCE-CHALLANGE/blob/main/train.csv",
        "source_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
        "target": "weekly_orders_per_centre_and_meal",
        "features": FEATURES,
        "selection": "lowest validation MAE on familiar series, weeks 117-129",
        "train_weeks": [13, 116],
        "validation_weeks": [117, 129],
        "test_weeks": [130, 145],
        "training_rows": len(train),
        "held_out_centres": held_centres.tolist(),
        "held_out_meals": held_meals.tolist(),
        "validation": validation_scores,
        "selected_model": winner,
        "test": test_scores,
        "test_protocol": "One week ahead rolling forecast; earlier true sales within held-out series are available as history",
    }
    artifact.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"estimator": model, "features": FEATURES, "report": report}, artifact)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    parser.add_argument("--artifact", type=Path, default=Path(__file__).parent / "global_meal_model.joblib")
    parser.add_argument("--report", type=Path, default=Path(__file__).parent / "global_meal_report.json")
    parser.add_argument("--forecast-week", type=int, help="Forecast a future week using data as one series of observed history")
    args = parser.parse_args()
    result = forecast(args.artifact, args.data, args.forecast_week) if args.forecast_week else run(args.data, args.artifact, args.report)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
