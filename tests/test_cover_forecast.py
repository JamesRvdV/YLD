import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from fastapi import HTTPException


class CoverForecastTest(unittest.TestCase):
    def test_auto_forecast_needs_fourteen_service_days(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_db = os.environ.get("YLD_DB_PATH")
            os.environ["YLD_DB_PATH"] = str(Path(temp_dir) / "demo.db")
            try:
                module_path = Path(__file__).resolve().parents[1] / "api" / "main.py"
                spec = importlib.util.spec_from_file_location("yld_cover_test", module_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

                automatic = module.plan(module.PlanInput())
                self.assertEqual(automatic["cover_source"], "forecast")
                self.assertEqual(automatic["covers"], automatic["forecast_covers"])
                self.assertGreaterEqual(automatic["cover_history_days"], 14)

                with module.db() as conn:
                    days = [row[0] for row in conn.execute("SELECT DISTINCT day FROM service_history ORDER BY day DESC LIMIT 13")]
                    placeholders = ",".join("?" for _ in days)
                    conn.execute(f"DELETE FROM service_history WHERE day NOT IN ({placeholders})", days)

                with self.assertRaises(HTTPException) as caught:
                    module.plan(module.PlanInput())
                self.assertEqual(caught.exception.status_code, 409)
                self.assertEqual(caught.exception.detail["code"], "covers_needed")
                self.assertEqual(caught.exception.detail["service_days"], 13)

                manual = module.plan(module.PlanInput(covers=75))
                self.assertEqual(manual["cover_source"], "manual")
                self.assertEqual(manual["covers"], 75)

                extra_day = (date.today() - timedelta(days=90)).isoformat()
                with module.db() as conn:
                    conn.execute("INSERT INTO service_history VALUES (?,?,?,?,?,?)", (extra_day, "short-rib", 15, 18, 3, 77))
                automatic = module.plan(module.PlanInput())
                self.assertEqual(automatic["cover_source"], "forecast")
                self.assertEqual(automatic["cover_history_days"], 14)
            finally:
                sys.modules.pop("yld_cover_test", None)
                if previous_db is None:
                    os.environ.pop("YLD_DB_PATH", None)
                else:
                    os.environ["YLD_DB_PATH"] = previous_db


if __name__ == "__main__":
    unittest.main()
