"""Compare higher-capacity cover models on chronological validation and holdout periods."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import joblib
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor

from cover_baseline import DATA_PATH, FEATURES, features, fit, load_services, predict, score


ARTIFACT_PATH = Path(__file__).parent / "cover_tree_model.joblib"
REPORT_PATH = Path(__file__).parent / "cover_model_comparison.json"


def candidates() -> dict:
    return {
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            max_iter=150, learning_rate=0.05, max_leaf_nodes=8,
            min_samples_leaf=20, l2_regularization=10,
            early_stopping=False, random_state=42,
        ),
        "random_forest": RandomForestRegressor(
            n_estimators=300, max_depth=6, min_samples_leaf=8,
            max_features=0.8, n_jobs=1, random_state=42,
        ),
        "extra_trees": ExtraTreesRegressor(
            n_estimators=300, max_depth=6, min_samples_leaf=8,
            max_features=0.8, n_jobs=1, random_state=42,
        ),
    }


def weekly_bootstrap_interval(days, ridge_errors, tree_errors, repeats=4000):
    """95% interval for ridge MAE minus tree MAE, resampling calendar weeks."""
    weeks = defaultdict(list)
    for day, ridge_error, tree_error in zip(days, ridge_errors, tree_errors):
        weeks[day.isocalendar()[:2]].append(ridge_error - tree_error)
    groups = list(weeks.values())
    rng = random.Random(42)
    differences = []
    for _ in range(repeats):
        sampled = [value for _ in groups for value in rng.choice(groups)]
        differences.append(sum(sampled) / len(sampled))
    differences.sort()
    return [round(differences[int(repeats * fraction)], 2) for fraction in (0.025, 0.975)]


def compare(data: Path, artifact: Path, report_path: Path) -> dict:
    services = load_services(data)
    samples = [features(services[:index], services[index][0]) for index in range(28, len(services))]
    targets = [covers for _, covers in services[28:]]
    validation = int(len(services) * 0.7) - 28
    holdout = int(len(services) * 0.8) - 28
    model_options = candidates()
    validation_scores = {}
    for name, model in model_options.items():
        model.fit(samples[:validation], targets[:validation])
        validation_scores[name] = score(targets[validation:holdout], model.predict(samples[validation:holdout]))
    ridge_validation = fit(samples[:validation], targets[:validation])
    validation_scores["ridge"] = score(
        targets[validation:holdout],
        [predict(ridge_validation, sample) for sample in samples[validation:holdout]],
    )
    winner = min(model_options, key=lambda name: validation_scores[name]["mae"])
    tree = candidates()[winner]
    tree.fit(samples[:holdout], targets[:holdout])
    ridge = fit(samples[:holdout], targets[:holdout])
    actual = targets[holdout:]
    tree_predictions = tree.predict(samples[holdout:])
    ridge_predictions = [predict(ridge, sample) for sample in samples[holdout:]]
    ridge_errors = [abs(observed - estimate) for observed, estimate in zip(actual, ridge_predictions)]
    tree_errors = [abs(observed - estimate) for observed, estimate in zip(actual, tree_predictions)]
    report = {
        "target": "inside_covers",
        "data_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
        "features": FEATURES,
        "selection": "Lowest validation MAE among the three tree models",
        "chosen_tree": winner,
        "train_end": services[validation + 27][0].isoformat(),
        "validation_start": services[validation + 28][0].isoformat(),
        "validation_end": services[holdout + 27][0].isoformat(),
        "holdout_start": services[holdout + 28][0].isoformat(),
        "holdout_end": services[-1][0].isoformat(),
        "validation_scores": validation_scores,
        "holdout_scores": {
            winner: score(actual, tree_predictions),
            "ridge": score(actual, ridge_predictions),
        },
        "ridge_mae_minus_tree_mae_95pct_weekly_bootstrap": weekly_bootstrap_interval(
            [day for day, _ in services[holdout + 28:]], ridge_errors, tree_errors,
        ),
        "final_train_services": len(services),
        "final_train_samples": len(samples),
        "one_step_ahead": True,
    }
    # The holdout stays unseen during selection and evaluation. Refit the saved
    # model on all observations only after scoring the holdout.
    final_model = candidates()[winner]
    final_model.fit(samples, targets)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"estimator": final_model, "features": FEATURES, "report": report}, artifact)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--artifact", type=Path, default=ARTIFACT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    print(json.dumps(compare(args.data, args.artifact, args.report), indent=2))


if __name__ == "__main__":
    main()
