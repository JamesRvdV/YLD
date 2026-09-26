"""Fixed trainer entry point. Runs only inside the networkless training container."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from api.modeling import MIN_SERVICES, fit, selection, validate_artifact


def train(snapshot, spec):
    selection(spec)
    if not isinstance(snapshot, dict) or set(snapshot) != {"dishes"} or not isinstance(snapshot["dishes"], list):
        raise ValueError("Invalid training snapshot")
    models = []
    for dish in snapshot["dishes"]:
        if not isinstance(dish, dict) or set(dish) != {"id", "rows"}:
            raise ValueError("Invalid dish data")
        if len(dish["rows"]) < MIN_SERVICES:
            continue
        models.append({"dish_id": dish["id"], **fit(dish["rows"], spec)})
    artifact = {"schema_version": 1, "algorithm": spec["algorithm"], "window": spec["window"], "penalty": spec["penalty"], "models": models}
    validate_artifact(artifact, {dish["id"] for dish in snapshot["dishes"]})
    return artifact


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: python -m api.train_container SNAPSHOT SELECTION OUTPUT")
    result = train(json.loads(Path(sys.argv[1]).read_text()), json.loads(Path(sys.argv[2]).read_text()))
    Path(sys.argv[3]).write_text(json.dumps(result, allow_nan=False, separators=(",", ":")))
