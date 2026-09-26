"""Bounded tools available to Codex inside its disposable container."""
from __future__ import annotations

import json
import sys
from bisect import bisect_left
from datetime import date
from pathlib import Path

from api.modeling import cover_estimate, fit, predict, selection, services_from_dishes


def inspect(snapshot):
    return {"dishes": [{"id": dish["id"], "services": len(dish["rows"]), "first_day": dish["rows"][0]["day"], "last_day": dish["rows"][-1]["day"]} for dish in snapshot["dishes"]]}


def trial(snapshot, spec):
    selection(spec)
    absolute_errors = []
    services = services_from_dishes(snapshot["dishes"])
    service_days = [service["day"] for service in services]
    for dish in snapshot["dishes"]:
        rows = dish["rows"]
        for index in range(max(28, len(rows) - 14), len(rows)):
            model = fit(rows[:index], spec)
            target_day = date.fromisoformat(rows[index]["day"])
            covers, _ = cover_estimate(services[:bisect_left(service_days, rows[index]["day"])], target_day)
            estimate, _ = predict(model, rows[index]["day"], covers)
            absolute_errors.append(abs(estimate - rows[index]["sold"]))
    return {"algorithm": spec["algorithm"], "window": spec["window"], "penalty": spec["penalty"], "observations": len(absolute_errors), "mae": round(sum(absolute_errors) / len(absolute_errors), 4) if absolute_errors else None}


if __name__ == "__main__":
    if len(sys.argv) not in (3, 6) or sys.argv[1] not in ("inspect", "trial"):
        raise SystemExit("usage: python3 -m api.agent_tools inspect SNAPSHOT | trial SNAPSHOT ALGORITHM WINDOW PENALTY")
    snapshot = json.loads(Path(sys.argv[2]).read_text())
    if sys.argv[1] == "inspect":
        if len(sys.argv) != 3:
            raise SystemExit("inspect takes no parameters")
        output = inspect(snapshot)
    else:
        if len(sys.argv) != 6:
            raise SystemExit("trial requires ALGORITHM, WINDOW and PENALTY")
        output = trial(snapshot, {"algorithm": sys.argv[3], "window": int(sys.argv[4]), "penalty": float(sys.argv[5]), "reason": "trial"})
    print(json.dumps(output, allow_nan=False))
