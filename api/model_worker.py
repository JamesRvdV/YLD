"""Host-side worker. Only this process may launch isolated agent/trainer containers."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
import uuid
from bisect import bisect_left
from pathlib import Path

from api import main
from api.modeling import MIN_SERVICES, cover_estimate, fit, predict, selection, services_from_dishes, supported, validate_artifact


AGENT_IMAGE = os.getenv("YLD_AGENT_IMAGE", "yld-model-agent:1")
TRAINER_IMAGE = os.getenv("YLD_TRAINER_IMAGE", "yld-model-trainer:1")
MAX_RUNTIME = 600


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def snapshot(workspace_id):
    with main.db() as conn:
        dishes = [dict(row) for row in conn.execute("SELECT id FROM workspace_dishes WHERE workspace_id=? ORDER BY id", (workspace_id,))]
        result = []
        for dish in dishes:
            rows = [dict(row) for row in conn.execute("SELECT day,sold,covers FROM workspace_history WHERE workspace_id=? AND dish_id=? ORDER BY day", (workspace_id, dish["id"]))]
            result.append({"id": dish["id"], "rows": rows})
    value = {"dishes": result}
    return value, hashlib.sha256(canonical(value).encode()).hexdigest()


def claim_job():
    with main.db() as conn:
        conn.execute("UPDATE model_jobs SET status='failed',finished_at=?,reason='Worker interrupted; start a new run.' WHERE status='running' AND started_at<?", (int(time.time()), int(time.time()) - 1800))
        row = conn.execute("SELECT id,workspace_id FROM model_jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
        if not row:
            return None
        claimed = conn.execute("UPDATE model_jobs SET status='running',stage='analyzing',started_at=? WHERE id=? AND status='queued'", (int(time.time()), row["id"]))
        return dict(row) if claimed.rowcount == 1 else None


def docker_run(image, work, data, args, *, network, key=False, prompt=None, proxy=None, timeout=MAX_RUNTIME):
    container_name = f"yld-model-{uuid.uuid4().hex}"
    command = ["docker", "run", "--rm", "--name", container_name, "--init", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64", "--memory=512m", "--cpus=1", "--user=65534:65534", "--network", network, "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m", "--mount", f"type=bind,src={data},dst=/data,readonly", "--mount", f"type=bind,src={work},dst=/work", "-e", "HOME=/work", "-e", "CODEX_HOME=/work/.codex", "-e", "PYTHONPATH=/opt/yld"]
    if prompt is not None:
        command.append("-i")
    if key:
        command += ["-e", "CODEX_API_KEY"]
    if proxy:
        command += ["-e", f"HTTPS_PROXY={proxy}", "-e", f"HTTP_PROXY={proxy}", "-e", f"https_proxy={proxy}", "-e", f"http_proxy={proxy}", "-e", "NO_PROXY=", "-e", "no_proxy="]
    command += [image, *args]
    try:
        result = subprocess.run(command, input=prompt, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
        raise RuntimeError("Isolated container timed out") from None
    if result.returncode:
        # Never save tool stdout/stderr: they may contain business data or secrets.
        raise RuntimeError(f"Isolated container exited with status {result.returncode}")


def run_agent(selection_snapshot, work, data):
    if not os.getenv("CODEX_API_KEY"):
        raise RuntimeError("CODEX_API_KEY is not configured for the worker")
    network = os.getenv("YLD_AGENT_NETWORK")
    proxy = os.getenv("YLD_AGENT_PROXY")
    if not network or not proxy:
        raise RuntimeError("YLD_AGENT_NETWORK and YLD_AGENT_PROXY are required")
    if not proxy.startswith("http://") or "@" in proxy:
        raise RuntimeError("YLD_AGENT_PROXY must be an HTTP proxy URL without credentials")
    inspected = subprocess.run(["docker", "network", "inspect", "--format", "{{.Internal}}", network], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False)
    if inspected.returncode or inspected.stdout.strip() != "true":
        raise RuntimeError("YLD_AGENT_NETWORK must be an internal Docker network")
    Path(data, "selection.json").write_text(canonical(selection_snapshot))
    codex_home = Path(work, ".codex")
    codex_home.mkdir(mode=0o777, exist_ok=True)
    os.chmod(codex_home, 0o777)
    prompt = ("You are YLD's model selection agent. The mounted /data/selection.json contains only opaque dish IDs and historic numeric service observations; the final 14 services per dish are withheld for a promotion test. "
              "Use the supplied tools by running `python3 -m api.agent_tools inspect /data/selection.json` and several `python3 -m api.agent_tools trial /data/selection.json ALGORITHM WINDOW PENALTY` commands. ALGORITHM is ridge_weekday_v1 or ridge_decay_v1; WINDOW is 28, 56 or 112; PENALTY is 0.5, 2, 10 or 50. "
              "Choose the best supported candidate based on trial MAE. Never edit tool code or data. Return only the exact JSON object required by the output schema. The reason must be a short factual explanation without customer data.")
    # Docker is the execution boundary: its read-only mounts, internal network,
    # dropped capabilities and resource limits remain in force. Codex's nested
    # bubblewrap sandbox cannot create user namespaces under those restrictions.
    command = ["codex", "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", "-C", "/work", "--output-schema", "/opt/yld/api/model_selection.schema.json", "--output-last-message", "/work/selection.json", "-",]
    # The prompt is passed over stdin, never through a shell.
    docker_run(AGENT_IMAGE, work, data, command, network=network, key=True, prompt=prompt, proxy=proxy)
    path = Path(work, "selection.json")
    if path.stat().st_size > 4096:
        raise ValueError("Selection exceeds size limit")
    value = json.loads(path.read_text())
    return selection(value)


def run_trainer(full_snapshot, spec, work, data):
    Path(data, "full.json").write_text(canonical(full_snapshot))
    Path(work, "selection.json").write_text(canonical(spec))
    docker_run(TRAINER_IMAGE, work, data, ["python", "-m", "api.train_container", "/data/full.json", "/work/selection.json", "/work/artifact.json"], network="none")
    path = Path(work, "artifact.json")
    if path.stat().st_size > 100_000:
        raise ValueError("Artifact exceeds size limit")
    return json.loads(path.read_text())


def gate(full_snapshot, spec, artifact):
    """Independent static and chronological gates; only passing dishes survive."""
    selection(spec)
    by_id = {dish["id"]: dish for dish in full_snapshot["dishes"]}
    services = services_from_dishes(full_snapshot["dishes"])
    service_days = [service["day"] for service in services]
    validate_artifact(artifact, set(by_id))
    if any(artifact[field] != spec[field] for field in ("algorithm", "window", "penalty")):
        raise ValueError("Artifact does not match the selected method")
    accepted = []
    detail = []
    for model in artifact["models"]:
        dish = by_id[model["dish_id"]]
        rows = dish["rows"]
        if len(rows) < MIN_SERVICES:
            raise ValueError("Model has insufficient history")
        expected = fit(rows, spec)
        if any(abs(a - b) > 1e-6 for a, b in zip(model["coefficients"], expected["coefficients"])) or any(model[field] != expected[field] for field in ("sigma", "min_covers", "max_covers", "max_sold")):
            raise ValueError("Trainer output does not reproduce")
        baseline_error = candidate_error = 0.0
        within_range = True
        for index in range(len(rows) - 14, len(rows)):
            actual = rows[index]
            prior = rows[:index]
            estimated_covers, _ = cover_estimate(services[:bisect_left(service_days, actual["day"])], main.date.fromisoformat(actual["day"]))
            baseline, _ = main.forecast(prior, estimated_covers, main.date.fromisoformat(actual["day"]), 0)
            rolling_model = fit(prior, spec)
            candidate, _ = predict(rolling_model, actual["day"], estimated_covers)
            within_range = within_range and supported(rolling_model, estimated_covers, candidate)
            baseline_error += abs(baseline - actual["sold"])
            candidate_error += abs(candidate - actual["sold"])
        baseline_mae = baseline_error / 14
        candidate_mae = candidate_error / 14
        passed = within_range and baseline_mae >= 0.1 and candidate_mae <= baseline_mae * 0.97 and baseline_mae - candidate_mae >= 0.1
        detail.append({"dish_id": model["dish_id"], "services_tested": 14, "baseline_mae": round(baseline_mae, 3), "candidate_mae": round(candidate_mae, 3), "passed": passed})
        if passed:
            accepted.append(model)
    eligible = {dish["id"] for dish in full_snapshot["dishes"] if len(dish["rows"]) >= MIN_SERVICES}
    if eligible != {entry["dish_id"] for entry in artifact["models"]}:
        raise ValueError("Trainer omitted an eligible dish")
    artifact = {**artifact, "models": accepted}
    metrics = {"gate": "chronological_14_services", "tested_dishes": len(detail), "promoted_dishes": len(accepted), "results": detail}
    return artifact, metrics


def finish_job(job_id, status, reason, data_hash=None, metrics=None):
    with main.db() as conn:
        conn.execute("UPDATE model_jobs SET status=?,finished_at=?,reason=?,data_hash=?,metrics_json=? WHERE id=? AND status='running'", (status, int(time.time()), reason[:240], data_hash, canonical(metrics) if metrics else None, job_id))


def set_stage(job_id, stage):
    if stage not in {"training", "validating", "promoting"}:
        raise ValueError("Unknown model job stage")
    with main.db() as conn:
        changed = conn.execute("UPDATE model_jobs SET stage=? WHERE id=? AND status='running'", (stage, job_id))
        if changed.rowcount != 1:
            raise RuntimeError("Model job was cancelled")


def process(job):
    full, original_hash = snapshot(job["workspace_id"])
    # Imported dish IDs are deterministic UUIDs derived from names. Give Codex
    # fresh, unrelated aliases so common menu names cannot be guessed from IDs.
    eligible = [{"id": uuid.uuid4().hex, "rows": dish["rows"][:-14]} for dish in full["dishes"] if len(dish["rows"]) >= MIN_SERVICES]
    if not eligible:
        finish_job(job["id"], "rejected", "At least one dish needs 56 recorded services.", original_hash)
        return
    with tempfile.TemporaryDirectory(prefix="yld-model-") as root:
        data = Path(root, "data")
        work = Path(root, "work")
        data.mkdir(mode=0o755)
        work.mkdir(mode=0o777)
        os.chmod(work, 0o777)
        spec = run_agent({"dishes": eligible}, str(work), str(data))
        set_stage(job["id"], "training")
        artifact = run_trainer(full, spec, str(work), str(data))
        set_stage(job["id"], "validating")
        artifact, metrics = gate(full, spec, artifact)
        metrics["selection"] = spec
    if not artifact["models"]:
        finish_job(job["id"], "rejected", "No trained dish model beat the existing forecast by 3% on held-out services.", original_hash, metrics)
        return
    _, current_hash = snapshot(job["workspace_id"])
    if current_hash != original_hash:
        finish_job(job["id"], "rejected", "Service history changed during training. Start a new run.", original_hash, metrics)
        return
    set_stage(job["id"], "promoting")
    version_id = str(uuid.uuid4())
    now = int(time.time())
    with main.db() as conn:
        # The import path locks the same workspace row before replacing data.
        conn.execute("UPDATE workspaces SET data_mode=data_mode WHERE id=?", (job["workspace_id"],))
        state = conn.execute("SELECT status FROM model_jobs WHERE id=?", (job["id"],)).fetchone()
        if not state or state["status"] != "running":
            return
        current = []
        for dish in conn.execute("SELECT id FROM workspace_dishes WHERE workspace_id=? ORDER BY id", (job["workspace_id"],)):
            rows = [dict(row) for row in conn.execute("SELECT day,sold,covers FROM workspace_history WHERE workspace_id=? AND dish_id=? ORDER BY day", (job["workspace_id"], dish["id"]))]
            current.append({"id": dish["id"], "rows": rows})
        if hashlib.sha256(canonical({"dishes": current}).encode()).hexdigest() != original_hash:
            raise ValueError("Service history changed during promotion")
        conn.execute("UPDATE model_versions SET status='archived' WHERE workspace_id=? AND status='active'", (job["workspace_id"],))
        conn.execute("INSERT INTO model_versions(id,workspace_id,status,artifact_json,metrics_json,data_hash,created_at,activated_at) VALUES (?,?,?,?,?,?,?,?)", (version_id, job["workspace_id"], "active", canonical(artifact), canonical(metrics), original_hash, now, now))
        conn.execute("UPDATE model_jobs SET status='promoted',stage='complete',finished_at=?,reason=?,data_hash=?,metrics_json=? WHERE id=?", (now, "Passed static and chronological gates", original_hash, canonical(metrics), job["id"]))


def run_once():
    job = claim_job()
    if not job:
        return False
    try:
        process(job)
    except Exception as error:
        finish_job(job["id"], "failed", type(error).__name__)
        raise
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] != "--once"):
        raise SystemExit("usage: python -m api.model_worker [--once]")
    if len(sys.argv) == 2:
        run_once()
    else:
        while True:
            try:
                worked = run_once()
            except Exception:
                worked = False
            if not worked:
                time.sleep(5)
