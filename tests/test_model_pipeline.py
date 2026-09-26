import copy
import base64
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from api.modeling import selection, services_from_dishes, validate_artifact
from api.train_container import train


SPEC = {"algorithm": "ridge_weekday_v1", "window": 56, "penalty": 0.5, "reason": "Lowest validation error"}


def sample_rows(days=84, pattern=True):
    start = date(2026, 1, 1)
    rows = []
    for index in range(days):
        day = start + timedelta(days=index)
        sold = ([4, 18, 9, 22, 8, 25, 6][day.weekday()] + index % 3) if pattern else 12
        rows.append({"day": day.isoformat(), "sold": sold, "covers": 65})
    return rows


class ModelPipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        from api import main
        from api import model_worker
        self.main = main
        self.worker = model_worker
        self.previous_db = main.DB_PATH
        main.DB_PATH = Path(self.temp.name, "test.db")
        main.init_db()

    def tearDown(self):
        self.main.DB_PATH = self.previous_db
        self.temp.cleanup()

    def seed(self, workspace_id="kitchen-1", dish_id="dish-1", rows=None):
        rows = rows or sample_rows()
        with self.main.db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at,data_mode) VALUES (?,?,?,?)", (workspace_id, "Test kitchen", 1, "imported"))
            conn.execute("INSERT INTO workspace_dishes VALUES (?,?,?,?,?,?,?,?,?)", (workspace_id, dish_id, "Soup", "MAINS", 12.0, 3.0, 12, 0, "Test"))
            conn.executemany("INSERT INTO workspace_history(workspace_id,day,dish_id,sold,prepared,leftover,covers,prep_known) VALUES (?,?,?,?,?,?,?,?)", [(workspace_id, row["day"], dish_id, row["sold"], row["sold"] + 2, 2, row["covers"], 1) for row in rows])
        return rows

    def test_hard_schemas_reject_executable_or_nonfinite_artifacts(self):
        self.assertEqual(selection(SPEC)["window"], 56)
        with self.assertRaises(ValueError):
            selection({**SPEC, "command": "curl example.com"})
        with self.assertRaises(ValueError):
            selection({**SPEC, "window": True})
        artifact = train({"dishes": [{"id": "dish-1", "rows": sample_rows()}]}, SPEC)
        validate_artifact(artifact, {"dish-1"})
        decay = train({"dishes": [{"id": "dish-1", "rows": sample_rows()}]}, {**SPEC, "algorithm": "ridge_decay_v1"})
        self.assertNotEqual(artifact["models"][0]["coefficients"], decay["models"][0]["coefficients"])
        for change in ({"dish_id": "other"}, {"coefficients": [float("nan")] * 10}, {"source": "import os"}):
            invalid = copy.deepcopy(artifact)
            invalid["models"][0].update(change)
            with self.assertRaises(ValueError):
                validate_artifact(invalid, {"dish-1"})

    def test_chronological_gate_promotes_only_improving_models(self):
        full = {"dishes": [{"id": "dish-1", "rows": sample_rows()}]}
        artifact, metrics = self.worker.gate(full, SPEC, train(full, SPEC))
        self.assertEqual(metrics["results"][0]["services_tested"], 14)
        self.assertEqual(metrics["promoted_dishes"], 1)
        self.assertEqual(len(artifact["models"]), 1)
        flat = {"dishes": [{"id": "dish-1", "rows": sample_rows(pattern=False)}]}
        artifact, metrics = self.worker.gate(flat, SPEC, train(flat, SPEC))
        self.assertEqual(metrics["promoted_dishes"], 0)
        self.assertEqual(artifact["models"], [])

    def test_worker_promotion_serves_model_only_to_own_workspace_and_import_archives_it(self):
        self.seed()
        self.seed("kitchen-2", "dish-2")
        with self.main.db() as conn:
            conn.execute("INSERT INTO model_jobs(id,workspace_id,status,created_at) VALUES (?,?,?,?)", ("job-1", "kitchen-1", "queued", 1))
        def current_stage():
            with self.main.db() as conn:
                return conn.execute("SELECT stage FROM model_jobs WHERE id='job-1'").fetchone()[0]
        def fake_agent(snapshot, work, data):
            self.assertEqual(current_stage(), "analyzing")
            self.assertEqual(len(snapshot["dishes"]), 1)
            self.assertNotEqual(snapshot["dishes"][0]["id"], "dish-1")
            self.assertEqual(len(snapshot["dishes"][0]["id"]), 32)
            self.assertEqual(len(snapshot["dishes"][0]["rows"]), 70)
            return SPEC
        def fake_trainer(snapshot, spec, work, data):
            self.assertEqual(current_stage(), "training")
            return train(snapshot, spec)
        original_gate = self.worker.gate
        def checking_gate(full, spec, artifact):
            self.assertEqual(current_stage(), "validating")
            return original_gate(full, spec, artifact)
        with patch.object(self.worker, "run_agent", side_effect=fake_agent), patch.object(self.worker, "run_trainer", side_effect=fake_trainer), patch.object(self.worker, "gate", side_effect=checking_gate):
            self.assertTrue(self.worker.run_once())
        with self.main.db() as conn:
            self.assertEqual(conn.execute("SELECT status FROM model_jobs WHERE id='job-1'").fetchone()[0], "promoted")
        self.assertEqual(current_stage(), "complete")
        first = self.main.build_plan("kitchen-1", 65, 0, 1.0)
        second = self.main.build_plan("kitchen-2", 65, 0, 1.0)
        self.assertEqual(first["dishes"][0]["forecast_source"], "trained")
        self.assertEqual(second["dishes"][0]["forecast_source"], "standard")
        self.assertIsNotNone(first["model_version"])
        self.assertTrue(first["insights"])
        self.assertEqual(self.main.build_plan("kitchen-1", 500, 0, 1.0)["dishes"][0]["forecast_source"], "standard")
        with self.main.db() as conn:
            original_artifact = conn.execute("SELECT artifact_json FROM model_versions WHERE workspace_id='kitchen-1'").fetchone()[0]
            conn.execute("UPDATE model_versions SET artifact_json='{}' WHERE workspace_id='kitchen-1'")
        self.assertEqual(self.main.build_plan("kitchen-1", 65, 0, 1.0)["dishes"][0]["forecast_source"], "standard")
        with self.main.db() as conn:
            conn.execute("UPDATE model_versions SET artifact_json=? WHERE workspace_id='kitchen-1'", (original_artifact,))
        self.assertEqual(self.main.rollback_model({"workspace_id": "kitchen-1", "role": "owner"}), {"ok": True})
        self.assertEqual(self.main.build_plan("kitchen-1", 65, 0, 1.0)["dishes"][0]["forecast_source"], "standard")
        # Reactivate to verify that replacing the import archives it as well.
        with self.main.db() as conn:
            conn.execute("UPDATE model_versions SET status='active' WHERE workspace_id='kitchen-1'")
            conn.execute("INSERT INTO model_jobs(id,workspace_id,status,created_at) VALUES (?,?,?,?)", ("job-queued", "kitchen-1", "queued", 2))
        lines = ["date,dish,sold,covers,prepared,ingredient_cost,price"]
        lines.extend(f"{row['day']},Soup,{row['sold']},65,{row['sold'] + 2},3.00,12.00" for row in sample_rows())
        self.main.commit_import(self.main.SalesCsvInput(csv_text="\n".join(lines)), {"workspace_id": "kitchen-1", "role": "owner"})
        self.assertIsNone(self.main.build_plan("kitchen-1", 65, 0, 1.0)["model_version"])
        with self.main.db() as conn:
            self.assertEqual(conn.execute("SELECT status FROM model_versions WHERE workspace_id='kitchen-1'").fetchone()[0], "archived")
            self.assertEqual(conn.execute("SELECT status FROM model_jobs WHERE id='job-queued'").fetchone()[0], "rejected")

    def test_spreadsheet_to_training_to_live_plan(self):
        with self.main.db() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at,data_mode) VALUES (?,?,?,?)", ("kitchen-1", "Test kitchen", 1, "empty"))
        user = {"workspace_id": "kitchen-1", "data_mode": "empty", "role": "owner"}
        source = "Trading Day,Menu Item,Qty,Pax\n" + "".join(
            f"{row['day']},Soup,{row['sold']},{row['covers']}\n" for row in sample_rows()
        )
        payload = self.main.SpreadsheetInput(filename="kitchen.csv", content_base64=base64.b64encode(source.encode()).decode())
        with patch.dict(os.environ, {"YLD_IMPORT_AGENT_API_KEY": "", "YLD_MODEL_WORKER_ENABLED": "1"}):
            inspected = self.main.inspect_spreadsheet(payload, user)
            self.assertEqual(inspected["mapping_source"], "rules")
            normalized = self.main.normalize_spreadsheet(
                self.main.MappedSpreadsheetInput(**payload.model_dump(), mapping=inspected["mapping"]), user
            )
            self.assertEqual(normalized["preview"]["services"], 84)
            self.assertEqual(normalized["preview"]["eligible_dishes"], 1)
            self.assertEqual(normalized["preview"]["dish_services"][0]["services"], 84)
            dish_id = normalized["preview"]["dish_costs"][0]["id"]
            self.main.commit_import(self.main.SalesCsvInput(
                csv_text=normalized["csv_text"],
                menu_costs={dish_id: self.main.DishCostsInput(ingredient_cost=3, price=12)},
                train=True,
                source_mapping=inspected["mapping"], source_signature=inspected["signature"],
            ), user)
            self.assertEqual(self.main.inspect_spreadsheet(payload, user)["mapping_source"], "saved")
            self.assertEqual(self.main.model_status(user)["job"]["status"], "queued")
            with patch.object(self.worker, "run_agent", return_value=SPEC), patch.object(
                self.worker, "run_trainer", side_effect=lambda full, spec, work, data: train(full, spec)
            ):
                self.assertTrue(self.worker.run_once())
            status = self.main.model_status(user)
            self.assertEqual(status["job"]["status"], "promoted")
            self.assertEqual(status["job"]["stage"], "complete")
            self.assertEqual(status["active"]["metrics"]["promoted_dishes"], 1)
            plan = self.main.build_plan("kitchen-1", 65, 0, 1.0)
            self.assertEqual(plan["dishes"][0]["forecast_source"], "trained")

    def test_stale_snapshot_cannot_be_promoted(self):
        self.seed()
        with self.main.db() as conn:
            conn.execute("INSERT INTO model_jobs(id,workspace_id,status,created_at) VALUES (?,?,?,?)", ("job-2", "kitchen-1", "queued", 1))
        def mutate_then_train(snapshot, spec, work, data):
            with self.main.db() as conn:
                conn.execute("UPDATE workspace_history SET sold=sold+1 WHERE workspace_id='kitchen-1'")
            return train(snapshot, spec)
        with patch.object(self.worker, "run_agent", return_value=SPEC), patch.object(self.worker, "run_trainer", side_effect=mutate_then_train):
            self.assertTrue(self.worker.run_once())
        with self.main.db() as conn:
            self.assertEqual(conn.execute("SELECT status FROM model_jobs WHERE id='job-2'").fetchone()[0], "rejected")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM model_versions").fetchone()[0], 0)

    def test_actuals_keep_new_services_but_retire_a_model_after_history_correction(self):
        rows = self.seed()
        artifact = train({"dishes": [{"id": "dish-1", "rows": rows}]}, SPEC)
        with self.main.db() as conn:
            conn.execute("INSERT INTO model_versions(id,workspace_id,status,artifact_json,metrics_json,data_hash,created_at,activated_at) VALUES (?,?,?,?,?,?,?,?)", ("version-1", "kitchen-1", "active", json.dumps(artifact), "{}", "old", 1, 1))
        user = {"workspace_id": "kitchen-1"}
        self.main.save_actual(self.main.ActualInput(day=self.main.local_today(), covers=65, dish_id="dish-1", prepared=14, sold=12), user)
        self.main.save_actual(self.main.ActualInput(day=date.fromisoformat(rows[0]["day"]), covers=65, dish_id="dish-1", prepared=rows[0]["sold"] + 3, sold=rows[0]["sold"]), user)
        with self.main.db() as conn:
            self.assertEqual(conn.execute("SELECT status FROM model_versions WHERE id='version-1'").fetchone()[0], "active")
            conn.execute("INSERT INTO model_jobs(id,workspace_id,status,created_at) VALUES (?,?,?,?)", ("job-correction", "kitchen-1", "queued", 2))
        self.main.save_actual(self.main.ActualInput(day=date.fromisoformat(rows[0]["day"]), covers=65, dish_id="dish-1", prepared=rows[0]["sold"] + 2, sold=rows[0]["sold"] + 1), user)
        with self.main.db() as conn:
            self.assertEqual(conn.execute("SELECT status FROM model_versions WHERE id='version-1'").fetchone()[0], "archived")
            self.assertEqual(conn.execute("SELECT status FROM model_jobs WHERE id='job-correction'").fetchone()[0], "rejected")

    def test_training_endpoint_checks_configuration_and_history(self):
        user = {"workspace_id": "kitchen-1", "role": "owner"}
        self.seed(rows=sample_rows(40))
        from fastapi import HTTPException
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("YLD_MODEL_WORKER_ENABLED", None)
            with self.assertRaises(HTTPException) as error:
                self.main.request_model_training(user)
            self.assertEqual(error.exception.status_code, 503)
        with patch.dict(os.environ, {"YLD_MODEL_WORKER_ENABLED": "1"}):
            with self.assertRaises(HTTPException) as error:
                self.main.request_model_training(user)
            self.assertEqual(error.exception.status_code, 409)
            with self.assertRaises(HTTPException) as error:
                self.main.request_model_training({"workspace_id": "kitchen-1", "role": "member"})
            self.assertEqual(error.exception.status_code, 403)

    def test_training_import_requires_menu_costs_and_reports_new_job(self):
        self.seed(rows=sample_rows(56))
        csv_text = "date,dish,sold,covers\n" + "".join(
            f"{row['day']},Soup,{row['sold']},{row['covers']}\n" for row in sample_rows(56)
        )
        user = {"workspace_id": "kitchen-1", "role": "owner"}
        with self.main.db() as conn:
            conn.execute("INSERT INTO model_jobs(id,workspace_id,status,created_at) VALUES (?,?,?,?)",
                         ("zzzz-older", "kitchen-1", "failed", int(self.main.time.time())))
        from fastapi import HTTPException
        with patch.dict(os.environ, {"YLD_MODEL_WORKER_ENABLED": "1"}):
            with self.assertRaises(HTTPException) as error:
                self.main.commit_import(self.main.SalesCsvInput(csv_text=csv_text, train=True), user)
            self.assertEqual(error.exception.status_code, 400)
            with self.main.db() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM workspace_history WHERE workspace_id=?", ("kitchen-1",)).fetchone()[0], 56)
            dish_id = str(self.main.uuid.uuid5(self.main.uuid.NAMESPACE_URL, "soup"))
            result = self.main.commit_import(self.main.SalesCsvInput(csv_text=csv_text, train=True,
                menu_costs={dish_id: self.main.DishCostsInput(ingredient_cost=3, price=12)}), user)
            self.assertEqual(result["training"]["status"], "queued")
            self.assertEqual(self.main.model_status(user)["job"]["id"], result["training"]["job_id"])

    def test_agent_rejects_a_network_with_direct_egress(self):
        data = Path(self.temp.name, "data")
        work = Path(self.temp.name, "work")
        data.mkdir()
        work.mkdir()
        with patch.dict(os.environ, {"CODEX_API_KEY": "test", "YLD_AGENT_NETWORK": "bridge", "YLD_AGENT_PROXY": "http://proxy:3128"}), patch.object(self.worker.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout="false")):
            with self.assertRaisesRegex(RuntimeError, "internal Docker network"):
                self.worker.run_agent({"dishes": []}, str(work), str(data))

    def test_agent_starts_with_writable_home_inside_the_external_sandbox(self):
        data = Path(self.temp.name, "data")
        work = Path(self.temp.name, "work")
        data.mkdir()
        work.mkdir()
        def finish_agent(_image, work_path, _data, command, **options):
            self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
            self.assertEqual(options["network"], "test-internal")
            self.assertTrue(options["key"])
            self.assertTrue(Path(work_path, ".codex").is_dir())
            Path(work_path, "selection.json").write_text(json.dumps(SPEC))
        with patch.dict(os.environ, {"CODEX_API_KEY": "test", "YLD_AGENT_NETWORK": "test-internal", "YLD_AGENT_PROXY": "http://proxy:3128"}), patch.object(self.worker.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout="true")), patch.object(self.worker, "docker_run", side_effect=finish_agent):
            self.assertEqual(self.worker.run_agent({"dishes": []}, str(work), str(data)), SPEC)

    def test_docker_execution_keeps_the_key_inside_the_agent_container(self):
        with patch.object(self.worker.os, "getuid", return_value=12345), patch.object(self.worker.os, "getgid", return_value=23456), patch.object(self.worker.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as launched:
            self.worker.docker_run("agent", "/tmp/work", "/tmp/data", ["codex", "exec"], network="internal", key=True, proxy="http://proxy:3128")
            agent_command = launched.call_args.args[0]
            self.assertIn("CODEX_API_KEY", agent_command)
            self.assertIn("--read-only", agent_command)
            self.assertIn("--cap-drop=ALL", agent_command)
            self.assertEqual(agent_command[agent_command.index("--user") + 1], "12345:23456")
            self.assertEqual(agent_command[agent_command.index("--network") + 1], "internal")
            self.worker.docker_run("trainer", "/tmp/work", "/tmp/data", ["python", "-m", "api.train_container"], network="none")
            trainer_command = launched.call_args.args[0]
            self.assertNotIn("CODEX_API_KEY", trainer_command)
            self.assertEqual(trainer_command[trainer_command.index("--network") + 1], "none")

    def test_docker_execution_rejects_root_worker(self):
        with patch.object(self.worker.os, "getuid", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "non-root"):
                self.worker.docker_run("agent", "/tmp/work", "/tmp/data", ["codex", "exec"], network="internal")

    def test_cover_history_uses_all_dishes_and_rejects_conflicts(self):
        dishes = [{"id": "a", "rows": [{"day": "2026-01-01", "covers": 30}, {"day": "2026-01-03", "covers": 40}]}, {"id": "b", "rows": [{"day": "2026-01-02", "covers": 35}, {"day": "2026-01-03", "covers": 40}]}]
        self.assertEqual([row["day"] for row in services_from_dishes(dishes)], ["2026-01-01", "2026-01-02", "2026-01-03"])
        dishes[1]["rows"][-1]["covers"] = 41
        with self.assertRaisesRegex(ValueError, "Inconsistent covers"):
            services_from_dishes(dishes)


if __name__ == "__main__":
    unittest.main()
