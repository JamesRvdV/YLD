"""Train a reproducible next-service restaurant cover baseline.

Only calendar information and covers from completed earlier services are features.
The evaluation simulates a forecast made after each previous service is recorded.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path


FEATURES = [
    "weekday_0", "weekday_1", "weekday_2", "weekday_3", "weekday_4",
    "weekday_5", "weekday_6", "last_service", "recent_7_mean",
    "recent_28_mean", "same_weekday_4_mean",
]
CONTINUOUS = range(7, len(FEATURES))
DATA_PATH = Path(__file__).parent / "data" / "restaurant_covers.csv"
MODEL_PATH = Path(__file__).parent / "cover_baseline.json"


def load_services(path: Path) -> list[tuple[date, int]]:
    services = []
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if not {"date", "inside_covers"}.issubset(reader.fieldnames or []):
            raise ValueError("Expected date and inside_covers columns")
        for line, row in enumerate(reader, 2):
            if not row["inside_covers"].strip():
                continue  # Closed service / no observed covers; never treat as zero demand.
            day = date.fromisoformat(row["date"])
            value = float(row["inside_covers"])
            if not value.is_integer() or value < 0:
                raise ValueError(f"Line {line}: invalid inside_covers")
            services.append((day, int(value)))
    services.sort()
    if len({day for day, _ in services}) != len(services):
        raise ValueError("Duplicate service dates")
    if len(services) < 60:
        raise ValueError("At least 60 observed services are needed")
    return services


def features(history: list[tuple[date, int]], target_day: date) -> list[float]:
    if len(history) < 28 or history[-1][0] >= target_day:
        raise ValueError("Need 28 earlier, completed services")
    recent = [covers for _, covers in history[-28:]]
    weekday = [covers for day, covers in reversed(history) if day.weekday() == target_day.weekday()][:4]
    if not weekday:
        raise ValueError("No earlier service on the target weekday")
    return [float(target_day.weekday() == day) for day in range(7)] + [
        float(recent[-1]), sum(recent[-7:]) / 7,
        sum(recent) / 28, sum(weekday) / len(weekday),
    ]


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a small ridge normal equation with partial pivoting."""
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(augmented[row][col]))
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        if abs(augmented[col][col]) < 1e-10:
            raise ValueError("Singular training matrix")
        scale = augmented[col][col]
        augmented[col] = [value / scale for value in augmented[col]]
        for row in range(size):
            if row == col:
                continue
            factor = augmented[row][col]
            augmented[row] = [left - factor * right for left, right in zip(augmented[row], augmented[col])]
    return [row[-1] for row in augmented]


def fit(samples: list[list[float]], targets: list[int], penalty: float = 20.0) -> dict:
    means = [0.0] * len(FEATURES)
    scales = [1.0] * len(FEATURES)
    for col in CONTINUOUS:
        means[col] = sum(sample[col] for sample in samples) / len(samples)
        variance = sum((sample[col] - means[col]) ** 2 for sample in samples) / len(samples)
        scales[col] = math.sqrt(variance) or 1.0
    transformed = [[1.0] + [(value - means[col]) / scales[col] for col, value in enumerate(sample)] for sample in samples]
    width = len(FEATURES) + 1
    gram = [[0.0] * width for _ in range(width)]
    rhs = [0.0] * width
    for sample, target in zip(transformed, targets):
        for col in range(width):
            rhs[col] += sample[col] * target
            for other in range(width):
                gram[col][other] += sample[col] * sample[other]
    for col in range(1, width):
        gram[col][col] += penalty
    return {"features": FEATURES, "means": means, "scales": scales,
            "coefficients": solve(gram, rhs), "penalty": penalty}


def predict(model: dict, sample: list[float]) -> float:
    scaled = [(value - model["means"][col]) / model["scales"][col]
              for col, value in enumerate(sample)]
    return max(0.0, model["coefficients"][0] +
               sum(weight * value for weight, value in zip(model["coefficients"][1:], scaled)))


def score(actual: list[int], predicted: list[float]) -> dict:
    errors = [estimate - observed for observed, estimate in zip(actual, predicted)]
    return {"mae": round(float(sum(abs(error) for error in errors) / len(errors)), 2),
            "rmse": round(float(math.sqrt(sum(error * error for error in errors) / len(errors))), 2)}


def train(services: list[tuple[date, int]]) -> dict:
    first_holdout = int(len(services) * 0.8)
    samples = [features(services[:index], services[index][0]) for index in range(28, len(services))]
    targets = [covers for _, covers in services[28:]]
    evaluation_model = fit(samples[:first_holdout - 28], targets[:first_holdout - 28])
    actual = targets[first_holdout - 28:]
    predicted = [predict(evaluation_model, sample) for sample in samples[first_holdout - 28:]]
    weekday_naive = []
    for index in range(first_holdout, len(services)):
        day = services[index][0]
        past = [covers for previous, covers in reversed(services[:index]) if previous.weekday() == day.weekday()][:4]
        weekday_naive.append(sum(past) / len(past))
    model = fit(samples, targets)
    model["training"] = {
        "target": "inside_covers", "evaluation_train_services": first_holdout,
        "evaluation_train_samples": first_holdout - 28,
        "final_train_services": len(services), "final_train_samples": len(samples),
        "holdout_services": len(actual),
        "train_end": services[first_holdout - 1][0].isoformat(),
        "holdout_start": services[first_holdout][0].isoformat(),
        "holdout_end": services[-1][0].isoformat(),
        "one_step_ahead": True,
        "model": score(actual, predicted),
        "same_weekday_last_4": score(actual, weekday_naive),
    }
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--output", type=Path, default=MODEL_PATH)
    args = parser.parse_args()
    services = load_services(args.data)
    model = train(services)
    model["training"]["data_sha256"] = hashlib.sha256(args.data.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(model["training"], indent=2))


if __name__ == "__main__":
    main()
