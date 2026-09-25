import asyncio
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse


def asgi_request(app, method, path, body=None, cookie=None, csrf=None, client_ip="127.0.0.1"):
    payload = json.dumps(body).encode() if body is not None else b""
    headers = [(b"host", b"testserver")]
    if body is not None:
        headers.append((b"content-type", b"application/json"))
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    if csrf:
        headers.append((b"x-csrf-token", csrf.encode()))
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "http_version": "1.1", "method": method, "scheme": "http", "path": path,
             "raw_path": path.encode(), "query_string": b"", "headers": headers, "client": (client_ip, 1), "server": ("testserver", 80)}
    asyncio.run(app(scope, receive, send))
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    response_headers = dict(next(message["headers"] for message in messages if message["type"] == "http.response.start"))
    response_body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    content_type = response_headers.get(b"content-type", b"").decode()
    decoded = json.loads(response_body) if response_body and "application/json" in content_type else response_body
    return status, response_headers, decoded


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db = os.environ.get("YLD_DB_PATH")
        os.environ["YLD_DB_PATH"] = str(Path(self.temp_dir.name) / "test.db")
        module_path = Path(__file__).resolve().parents[1] / "api" / "main.py"
        self.module_name = "yld_auth_test"
        spec = importlib.util.spec_from_file_location(self.module_name, module_path)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[self.module_name] = self.module
        spec.loader.exec_module(self.module)

    def tearDown(self):
        sys.modules.pop(self.module_name, None)
        if self.previous_db is None:
            os.environ.pop("YLD_DB_PATH", None)
        else:
            os.environ["YLD_DB_PATH"] = self.previous_db
        self.temp_dir.cleanup()

    def redeem(self, email, workspace):
        link = self.module.issue_invite(email, workspace_name=workspace, send=False)
        token = parse_qs(urlparse(link).fragment)["token"][0]
        status, headers, _ = asgi_request(self.module.app, "POST", "/api/auth/redeem", {"token": token})
        self.assertEqual(status, 200)
        cookies = SimpleCookie()
        cookies.load(headers[b"set-cookie"].decode())
        cookie = f"yld_session={cookies['yld_session'].value}"
        status, _, result = asgi_request(self.module.app, "GET", "/api/auth/me", cookie=cookie)
        self.assertEqual(status, 200)
        return token, cookie, result["user"]

    def service_csv(self, dish="Soup", ingredient_cost="3.00", price="12.00", days=16):
        lines = ["date,dish,sold,covers,prepared,ingredient_cost,price,category"]
        today = self.module.local_today()
        for days_ago in range(days, 0, -1):
            day = (today - self.module.timedelta(days=days_ago)).isoformat()
            lines.append(f"{day},{dish},{10 + days_ago % 3},55,{14 + days_ago % 3},{ingredient_cost},{price},MAINS")
        return "\n".join(lines)

    def test_invite_session_and_workspace_isolation(self):
        status, _, _ = asgi_request(self.module.app, "POST", "/api/plan", {})
        self.assertEqual(status, 401)
        first_token, first_cookie, first = self.redeem("chef@first.example", "First Kitchen")
        _, second_cookie, second = self.redeem("chef@second.example", "Second Kitchen")
        self.assertNotEqual(first["workspace_id"], second["workspace_id"])
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/auth/redeem", {"token": first_token})[0], 400)
        self.assertEqual(first["data_mode"], "empty")
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=first_cookie)[2]["detail"]["code"], "import_needed")
        for cookie, user in ((first_cookie, first), (second_cookie, second)):
            status, _, _ = asgi_request(self.module.app, "POST", "/api/import/commit", {"csv_text": self.service_csv()}, cookie=cookie, csrf=user["csrf_token"])
            self.assertEqual(status, 200)
        first_initial = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=first_cookie)[2]
        dish_id = first_initial["dishes"][0]["id"]

        status, _, _ = asgi_request(self.module.app, "PATCH", f"/api/dishes/{dish_id}", {"ingredient_cost": 5, "price": 20}, cookie=first_cookie)
        self.assertEqual(status, 403)
        status, _, _ = asgi_request(self.module.app, "PATCH", f"/api/dishes/{dish_id}", {"ingredient_cost": 5, "price": 20}, cookie=first_cookie, csrf=first["csrf_token"])
        self.assertEqual(status, 200)
        status, _, first_plan = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=first_cookie)
        self.assertEqual(status, 200)
        status, _, second_plan = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=second_cookie)
        self.assertEqual(status, 200)
        first_cost = first_plan["dishes"][0]["ingredient_cost"]
        second_cost = second_plan["dishes"][0]["ingredient_cost"]
        self.assertEqual(first_cost, 5)
        self.assertEqual(second_cost, 3)
        self.assertEqual(first_plan["cover_source"], "forecast")

        status, _, _ = asgi_request(self.module.app, "POST", "/api/auth/logout", cookie=first_cookie, csrf=first["csrf_token"])
        self.assertEqual(status, 200)
        self.assertEqual(asgi_request(self.module.app, "GET", "/api/auth/me", cookie=first_cookie)[0], 401)

    def test_csv_import_replaces_only_owner_workspace_and_handles_unknown_prep(self):
        _, owner_cookie, owner = self.redeem("owner@first.example", "First Kitchen")
        _, other_cookie, other = self.redeem("owner@second.example", "Second Kitchen")
        csv_text = "date,dish,sold,covers,ingredient_cost,price\n"
        today = self.module.local_today()
        for days_ago in range(16, 0, -1):
            csv_text += f"{(today - self.module.timedelta(days=days_ago)).isoformat()},Soup,{8 + days_ago % 3},40,2.50,12.00\n"
        body = {"csv_text": csv_text}
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/import/commit", body, cookie=owner_cookie)[0], 403)
        status, _, preview = asgi_request(self.module.app, "POST", "/api/import/preview", body, cookie=owner_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(preview["prepared_rows"], 0)
        status, _, result = asgi_request(self.module.app, "POST", "/api/import/commit", body, cookie=owner_cookie, csrf=owner["csrf_token"])
        self.assertEqual(status, 200)
        self.assertEqual(result["services"], 16)
        status, _, own_plan = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=owner_cookie)
        self.assertEqual(status, 200)
        self.assertEqual([dish["name"] for dish in own_plan["dishes"]], ["Soup"])
        self.assertIsNone(own_plan["summary"]["usual_waste"])
        self.assertFalse(own_plan["backtest"]["available"])
        status, _, other_plan = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=other_cookie)
        self.assertEqual(status, 409)
        self.assertEqual(other_plan["detail"]["code"], "import_needed")
        self.assertEqual(other["data_mode"], "empty")

    def test_expired_invite_is_rejected(self):
        link = self.module.issue_invite("chef@example.com", workspace_name="Sample Kitchen", send=False)
        token = parse_qs(urlparse(link).fragment)["token"][0]
        with self.module.db() as conn:
            conn.execute("UPDATE auth_links SET expires_at=0 WHERE token_hash=?", (self.module.token_hash(token),))
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/auth/redeem", {"token": token})[0], 400)

    def test_resend_invitation_payload(self):
        result = MagicMock()
        result.__enter__.return_value.status = 200
        with patch.dict(os.environ, {"RESEND_API_KEY": "test-key", "YLD_EMAIL_FROM": "YLD <invites@example.com>"}), patch.object(self.module, "urlopen", return_value=result) as send:
            self.module.send_link_email("chef@example.com", "A & B Kitchen", "https://example.com/invite#token=secret", "invite", "invite-123")
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(request.get_header("Idempotency-key"), "invite-123")
        payload = json.loads(request.data)
        self.assertEqual(payload["to"], ["chef@example.com"])
        self.assertIn("A &amp; B Kitchen", payload["html"])
        self.assertIn("https://example.com/invite#token=secret", payload["text"])

    def test_existing_account_gets_login_link_without_account_enumeration(self):
        self.redeem("chef@example.com", "Sample Kitchen")
        with patch.dict(os.environ, {"RESEND_API_KEY": "test-key", "YLD_EMAIL_FROM": "YLD <invites@example.com>"}), patch.object(self.module, "send_signin_email") as send:
            status, _, known = asgi_request(self.module.app, "POST", "/api/auth/request-link", {"email": "chef@example.com"})
            self.assertEqual(status, 200)
            self.assertEqual(send.call_count, 1)
            login_link = send.call_args.args[2]
            status, _, unknown = asgi_request(self.module.app, "POST", "/api/auth/request-link", {"email": "absent@example.com"})
            self.assertEqual(status, 200)
            self.assertEqual(known, unknown)
            self.assertEqual(send.call_count, 1)
        token = parse_qs(urlparse(login_link).fragment)["token"][0]
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/auth/redeem", {"token": token})[0], 200)

    def test_login_requires_email_delivery(self):
        self.redeem("chef@example.com", "Test Kitchen")
        with patch.dict(os.environ, {"RESEND_API_KEY": "", "YLD_EMAIL_FROM": ""}):
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/auth/request-link", {"email": "chef@example.com"})[0], 503)

    def test_old_generated_workspace_is_cleared_on_startup(self):
        _, owner_cookie, owner = self.redeem("owner@example.com", "Former Kitchen")
        member_link = self.module.issue_invite("member@example.com", workspace_id=owner["workspace_id"], send=False)
        member_token = parse_qs(urlparse(member_link).fragment)["token"][0]
        status, headers, _ = asgi_request(self.module.app, "POST", "/api/auth/redeem", {"token": member_token})
        self.assertEqual(status, 200)
        cookies = SimpleCookie()
        cookies.load(headers[b"set-cookie"].decode())
        member_cookie = f"yld_session={cookies['yld_session'].value}"
        member = asgi_request(self.module.app, "GET", "/api/auth/me", cookie=member_cookie)[2]["user"]
        self.assertEqual(member["workspace_id"], owner["workspace_id"])
        with self.module.db() as conn:
            conn.execute("INSERT INTO workspace_dishes VALUES (?,?,?,?,?,?,?,?,?)", (owner["workspace_id"], "old", "Old dish", "MAINS", 10, 3, 5, 0, ""))
            conn.execute("INSERT INTO workspace_history(workspace_id,day,dish_id,sold,prepared,leftover,covers) VALUES (?,?,?,?,?,?,?)", (owner["workspace_id"], "2026-01-01", "old", 5, 8, 3, 50))
            conn.execute("CREATE TABLE dishes (name TEXT)")
            conn.execute("INSERT INTO dishes VALUES ('Generated dish')")
            conn.execute("UPDATE workspaces SET data_mode='sample' WHERE id=?", (owner["workspace_id"],))
        self.module.init_db()
        with self.module.db() as conn:
            self.assertEqual(conn.execute("SELECT data_mode FROM workspaces WHERE id=?", (owner["workspace_id"],)).fetchone()[0], "empty")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM workspace_dishes WHERE workspace_id=?", (owner["workspace_id"],)).fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM workspace_history WHERE workspace_id=?", (owner["workspace_id"],)).fetchone()[0], 0)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dishes'").fetchone())
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=owner_cookie)[2]["detail"]["code"], "import_needed")

    def test_csv_import_builds_plan_from_empty_workspace(self):
        _, cookie, user = self.redeem("owner@example.com", "Real Kitchen")
        lines = ["date,dish,sold,covers,prepared,ingredient_cost,price,category"]
        for days_ago in range(28, 0, -1):
            day = (self.module.local_today() - timedelta(days=days_ago)).isoformat()
            lines.append(f"{day},Fish tacos,{17 + days_ago % 5},72,{22 + days_ago % 5},6.50,19.00,MAINS")
            lines.append(f"{day},Apple tart,{8 + days_ago % 3},72,{11 + days_ago % 3},2.80,12.00,DESSERT")
        csv_text = "\n".join(lines)
        status, _, preview = asgi_request(self.module.app, "POST", "/api/import/preview", {"csv_text": csv_text}, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual((preview["services"], preview["dishes"], preview["prepared_rows"]), (28, 2, 56))
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/import/commit", {"csv_text": csv_text}, cookie=cookie)[0], 403)
        status, _, imported = asgi_request(self.module.app, "POST", "/api/import/commit", {"csv_text": csv_text}, cookie=cookie, csrf=user["csrf_token"])
        self.assertEqual(status, 200)
        self.assertEqual(imported["rows"], 56)
        status, _, plan = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual({dish["name"] for dish in plan["dishes"]}, {"Fish tacos", "Apple tart"})
        self.assertEqual(plan["cover_source"], "forecast")
        self.assertTrue(plan["backtest"]["available"])
        self.assertEqual(asgi_request(self.module.app, "GET", "/api/auth/me", cookie=cookie)[2]["user"]["data_mode"], "imported")
        status, headers, export = asgi_request(self.module.app, "GET", "/api/export/history", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b"text/csv", headers[b"content-type"])
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/import/preview", {"csv_text": export.decode()}, cookie=cookie)[2]["rows"], 56)

    def test_sales_only_import_does_not_fabricate_waste_and_invalid_file_is_atomic(self):
        _, cookie, user = self.redeem("owner@example.com", "Real Kitchen")
        lines = ["date,dish,sold,covers,ingredient_cost,price"]
        for days_ago in range(20, 0, -1):
            day = (self.module.local_today() - timedelta(days=days_ago)).isoformat()
            lines.append(f"{day},Soup,{12 + days_ago % 3},55,3.00,12.00")
        csv_text = "\n".join(lines)
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/import/commit", {"csv_text": csv_text}, cookie=cookie, csrf=user["csrf_token"])[0], 200)
        plan = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=cookie)[2]
        self.assertEqual(len(plan["dishes"]), 1)
        self.assertIsNone(plan["summary"]["usual_waste"])
        self.assertFalse(plan["backtest"]["available"])
        bad_csv = csv_text + "\n" + lines[-1]
        status, _, body = asgi_request(self.module.app, "POST", "/api/import/commit", {"csv_text": bad_csv}, cookie=cookie, csrf=user["csrf_token"])
        self.assertEqual(status, 400)
        self.assertIn("duplicate", body["detail"])
        self.assertEqual(len(asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=cookie)[2]["dishes"]), 1)
        today = self.module.local_today().isoformat()
        dish_id = plan["dishes"][0]["id"]
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/actuals", {"day": today, "covers": 55, "dish_id": dish_id, "prepared": 18, "sold": 15}, cookie=cookie, csrf=user["csrf_token"])[0], 200)
        updated = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=cookie)[2]
        self.assertEqual(updated["summary"]["usual_waste"], 9)

    def test_backtest_counts_distinct_service_dates_with_sparseness(self):
        _, cookie, user = self.redeem("owner@example.com", "Changing Menu")
        lines = ["date,dish,sold,covers,prepared,ingredient_cost,price"]
        for days_ago in range(15, 0, -1):
            day = (self.module.local_today() - timedelta(days=days_ago)).isoformat()
            lines.append(f"{day},Soup,10,50,13,3.00,12.00")
            if days_ago == 1:
                lines.append(f"{day},New salad,7,50,9,2.00,10.00")
        status, _, _ = asgi_request(self.module.app, "POST", "/api/import/commit", {"csv_text": "\n".join(lines)}, cookie=cookie, csrf=user["csrf_token"])
        self.assertEqual(status, 200)
        status, _, plan = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertTrue(plan["backtest"]["available"])
        self.assertEqual(plan["backtest"]["days"], 1)

    def test_optimizer_matches_full_search_and_extreme_cost_ratio(self):
        def full_search(mu, sigma, ingredient_cost, shortage_cost, waste_weight):
            options = []
            for qty in range(101):
                z = (qty - mu) / sigma
                over = sigma * (self.module.normal_pdf(z) + z * self.module.normal_cdf(z))
                under = sigma * (self.module.normal_pdf(z) - z * (1 - self.module.normal_cdf(z)))
                options.append((over * ingredient_cost * waste_weight + under * shortage_cost, qty))
            return min(options)

        cases = [(10, 2, 3, 8, 1), (0.2, 1.8, 3, 8, 1), (30, 7, 5, 2, 2), (20, 1, 0.01, 9999, 1)]
        for args in cases:
            with self.subTest(args=args):
                cost, qty, _, _ = self.module.optimize(*args)
                brute_cost, brute_qty = full_search(*args)
                self.assertEqual(qty, brute_qty)
                self.assertAlmostEqual(cost, brute_cost, places=6)
        self.assertGreater(self.module.optimize(*cases[-1])[1], math.ceil(20 + 4 * 1))

    def test_actual_covers_update_the_whole_service(self):
        _, cookie, user = self.redeem("owner@example.com", "Service Covers")
        first_day = (self.module.local_today() - timedelta(days=2)).isoformat()
        second_day = (self.module.local_today() - timedelta(days=1)).isoformat()
        csv_text = "\n".join([
            "date,dish,sold,covers,prepared,ingredient_cost,price",
            f"{first_day},Soup,10,55,14,3.00,12.00",
            f"{first_day},Salad,8,55,10,2.00,10.00",
            f"{second_day},Soup,11,55,14,3.00,12.00",
            f"{second_day},Salad,9,55,11,2.00,10.00",
        ])
        status, _, _ = asgi_request(self.module.app, "POST", "/api/import/commit", {"csv_text": csv_text}, cookie=cookie, csrf=user["csrf_token"])
        self.assertEqual(status, 200)
        with self.module.db() as conn:
            dish_id = conn.execute("SELECT id FROM workspace_dishes WHERE workspace_id=? AND name='Soup'", (user["workspace_id"],)).fetchone()[0]
        status, _, _ = asgi_request(self.module.app, "POST", "/api/actuals", {"day": first_day, "covers": 70, "dish_id": dish_id, "prepared": 15, "sold": 11}, cookie=cookie, csrf=user["csrf_token"])
        self.assertEqual(status, 200)
        with self.module.db() as conn:
            corrected = [row[0] for row in conn.execute("SELECT covers FROM workspace_history WHERE workspace_id=? AND day=?", (user["workspace_id"], first_day))]
            untouched = [row[0] for row in conn.execute("SELECT covers FROM workspace_history WHERE workspace_id=? AND day=?", (user["workspace_id"], second_day))]
        self.assertEqual(corrected, [70, 70])
        self.assertEqual(untouched, [55, 55])

    def test_sales_csv_without_cost_columns_uses_preview_cost_entry(self):
        _, cookie, user = self.redeem("owner@example.com", "Cost Setup")
        lines = ["date,dish,sold,covers"]
        for days_ago in range(16, 0, -1):
            day = (self.module.local_today() - timedelta(days=days_ago)).isoformat()
            lines.append(f"{day},Pumpkin soup,{10 + days_ago % 4},54")
        csv_text = "\n".join(lines)
        status, _, preview = asgi_request(self.module.app, "POST", "/api/import/preview", {"csv_text": csv_text}, cookie=cookie)
        self.assertEqual(status, 200)
        dish = preview["dish_costs"][0]
        self.assertEqual(dish["name"], "Pumpkin soup")
        self.assertIsNone(dish["ingredient_cost"])
        self.assertIsNone(dish["price"])
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/import/commit", {"csv_text": csv_text}, cookie=cookie, csrf=user["csrf_token"])[0], 400)
        original = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=cookie)[2]
        self.assertEqual(original["detail"]["code"], "import_needed")
        costs = {dish["id"]: {"ingredient_cost": 2.75, "price": 11.5}}
        status, _, _ = asgi_request(self.module.app, "POST", "/api/import/commit", {"csv_text": csv_text, "menu_costs": costs}, cookie=cookie, csrf=user["csrf_token"])
        self.assertEqual(status, 200)
        plan = asgi_request(self.module.app, "POST", "/api/plan", {}, cookie=cookie)[2]
        self.assertEqual(plan["dishes"][0]["name"], "Pumpkin soup")
        self.assertEqual(plan["dishes"][0]["ingredient_cost"], 2.75)

    def test_preview_cli_prints_link_but_production_refuses(self):
        project_root = Path(__file__).resolve().parents[1]
        command = [sys.executable, "-m", "api.invite", "--email", "owner@example.com", "--workspace", "Preview Kitchen", "--print-link"]
        environment = {**os.environ, "YLD_DB_PATH": str(Path(self.temp_dir.name) / "cli.db"), "YLD_PUBLIC_URL": "https://yld.nz", "YLD_ENV": "preview"}
        preview = subprocess.run(command, cwd=project_root, env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertTrue(preview.stdout.strip().startswith("https://yld.nz/invite#token="))

        production = subprocess.run(command, cwd=project_root, env={**environment, "YLD_ENV": "production", "RESEND_API_KEY": "test-only", "YLD_EMAIL_FROM": "YLD <invites@example.com>"}, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(production.returncode, 0)
        self.assertIn("--print-link is disabled in production", production.stderr)

    def test_https_session_cookie_is_secure(self):
        with patch.object(self.module, "PUBLIC_URL", "https://yld.example"):
            link = self.module.issue_invite("chef@example.com", workspace_name="Sample Kitchen", send=False)
            token = parse_qs(urlparse(link).fragment)["token"][0]
            status, headers, _ = asgi_request(self.module.app, "POST", "/api/auth/redeem", {"token": token})
            self.assertEqual(status, 200)
            self.assertIn(b"Secure", headers[b"set-cookie"])
            self.assertEqual(headers[b"strict-transport-security"], b"max-age=31536000")

    def test_built_site_serves_invite_route(self):
        if not (Path(__file__).resolve().parents[1] / "dist" / "index.html").exists():
            self.skipTest("Run npm run build to check production routing")
        status, headers, body = asgi_request(self.module.app, "GET", "/invite")
        self.assertEqual(status, 200)
        self.assertIn(b"text/html", headers[b"content-type"])
        self.assertIn(b'<div id="root"></div>', body)


if __name__ == "__main__":
    unittest.main()
