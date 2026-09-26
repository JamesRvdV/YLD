import asyncio
import hashlib
import hmac
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, Request
from test_auth import asgi_request


class BillingTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "YLD_DB_PATH": str(Path(self.temp_dir.name) / "billing.db"),
            "YLD_STRIPE_TEST_CHECKOUT": "1",
            "STRIPE_SECRET_KEY": "sk_test_example",
            "STRIPE_WEBHOOK_SECRET": "whsec_example",
            "STRIPE_PRICE_LOCAL": "price_local_test",
            "STRIPE_PRICE_MULTI_CHAIN": "price_multi_test",
        })
        self.env.start()
        module_path = Path(__file__).resolve().parents[1] / "api" / "main.py"
        self.module_name = "yld_billing_test"
        spec = importlib.util.spec_from_file_location(self.module_name, module_path)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[self.module_name] = self.module
        spec.loader.exec_module(self.module)
        link = self.module.issue_invite("owner@example.com", workspace_name="Test Kitchen", send=False)
        token = parse_qs(urlparse(link).fragment)["token"][0]
        status, headers, _ = asgi_request(self.module.app, "POST", "/api/auth/redeem", {"token": token, "password": "a-strong-test-password"})
        self.assertEqual(status, 200)
        cookies = SimpleCookie()
        cookies.load(headers[b"set-cookie"].decode())
        self.cookie = f"yld_session={cookies['yld_session'].value}"
        self.user = asgi_request(self.module.app, "GET", "/api/auth/me", cookie=self.cookie)[2]["user"]

    def tearDown(self):
        sys.modules.pop(self.module_name, None)
        self.env.stop()
        self.temp_dir.cleanup()

    def webhook(self, event, valid=True):
        body = json.dumps(event).encode()
        timestamp = int(time.time())
        digest = hmac.new(b"whsec_example", str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
        signature = f"t={timestamp},v1={'0' * 64 if not valid else digest}"
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        request = Request({"type": "http", "method": "POST", "headers": [(b"stripe-signature", signature.encode())]}, receive)
        return asyncio.run(self.module.billing_webhook(request))

    def test_checkout_requires_owner_session_csrf_and_allowlisted_plan(self):
        session = SimpleNamespace(id="cs_test", url="https://checkout.stripe.com/test", expires_at=int(time.time()) + 1800)
        with patch.object(self.module.stripe.checkout.Session, "create", return_value=session) as create:
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"})[0], 401)
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie)[0], 403)
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "enterprise"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 400)
            status, _, body = asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])
            self.assertEqual(status, 200)
            self.assertEqual(body["url"], "https://checkout.stripe.com/test")
            self.assertEqual(create.call_args.kwargs["line_items"][0]["price"], "price_local_test")
            self.assertEqual(create.call_args.kwargs["subscription_data"]["metadata"]["workspace_id"], self.user["workspace_id"])
            status, _, repeated = asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])
            self.assertEqual((status, repeated["url"]), (200, session.url))
            self.assertEqual(create.call_count, 1)
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "multi_chain"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 409)
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_live_wrong"}):
            self.assertEqual(asgi_request(self.module.app, "GET", "/api/billing/config")[2]["test_checkout_enabled"], False)
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 503)

    def test_cancelled_checkout_can_be_expired_before_switching_plans(self):
        session = SimpleNamespace(id="cs_test", url="https://checkout.stripe.com/test", expires_at=int(time.time()) + 1800)
        with patch.object(self.module.stripe.checkout.Session, "create", return_value=session) as create, \
             patch.object(self.module.stripe.checkout.Session, "retrieve", return_value=SimpleNamespace(status="open")), \
             patch.object(self.module.stripe.checkout.Session, "expire") as expire:
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 200)
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout/abandon", cookie=self.cookie, csrf=self.user["csrf_token"])[0], 200)
            expire.assert_called_once_with("cs_test")
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "multi_chain"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 200)
            self.assertEqual(create.call_count, 2)

    def test_checkout_retry_reuses_idempotency_key_after_stripe_error(self):
        session = SimpleNamespace(id="cs_test", url="https://checkout.stripe.com/test", expires_at=int(time.time()) + 1800)
        with patch.object(self.module.stripe.checkout.Session, "create", side_effect=[RuntimeError("timeout"), session]) as create:
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 502)
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 200)
            self.assertEqual(create.call_args_list[0].kwargs["idempotency_key"], create.call_args_list[1].kwargs["idempotency_key"])

    def test_owner_can_reconcile_completed_checkout_without_webhook(self):
        checkout = SimpleNamespace(id="cs_test", url="https://checkout.stripe.com/test", expires_at=int(time.time()) + 1800)
        completed = SimpleNamespace(status="complete", subscription="sub_test")
        subscription = {"id": "sub_test", "customer": "cus_test", "status": "active", "created": int(time.time()), "livemode": False,
                        "metadata": {"workspace_id": self.user["workspace_id"], "plan": "local"}}
        with patch.object(self.module.stripe.checkout.Session, "create", return_value=checkout), \
             patch.object(self.module.stripe.checkout.Session, "retrieve", return_value=completed), \
             patch.object(self.module.stripe.Subscription, "retrieve", return_value=subscription):
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 200)
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout/verify", cookie=self.cookie)[0], 403)
            status, _, result = asgi_request(self.module.app, "POST", "/api/billing/checkout/verify", cookie=self.cookie, csrf=self.user["csrf_token"])
            self.assertEqual(status, 200)
            self.assertEqual(result, {"billing": {"plan": "local", "status": "active"}, "checkout": "complete"})
            self.assertEqual(asgi_request(self.module.app, "GET", "/api/billing/status", cookie=self.cookie)[2]["billing"], result["billing"])
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 409)

    def test_expired_checkout_can_be_restarted(self):
        checkout = SimpleNamespace(id="cs_test", url="https://checkout.stripe.com/test", expires_at=int(time.time()) + 1800)
        with patch.object(self.module.stripe.checkout.Session, "create", return_value=checkout) as create, \
             patch.object(self.module.stripe.checkout.Session, "retrieve", return_value=SimpleNamespace(status="expired")):
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 200)
            status, _, result = asgi_request(self.module.app, "POST", "/api/billing/checkout/verify", cookie=self.cookie, csrf=self.user["csrf_token"])
            self.assertEqual((status, result["checkout"]), (200, "expired"))
            self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "multi_chain"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 200)
            self.assertEqual(create.call_count, 2)

    def test_signed_subscription_updates_status_and_opens_portal(self):
        event = {"id": "evt_test", "type": "customer.subscription.created", "created": int(time.time()), "livemode": False,
                 "data": {"object": {"id": "sub_test", "customer": "cus_test", "status": "active",
                                     "metadata": {"workspace_id": self.user["workspace_id"], "plan": "local"}}}}
        with self.assertRaises(HTTPException) as invalid:
            self.webhook(event, valid=False)
        self.assertEqual(invalid.exception.status_code, 400)
        self.assertEqual(self.webhook(event), {"received": True})
        self.assertEqual(asgi_request(self.module.app, "GET", "/api/billing/status", cookie=self.cookie)[2]["billing"], {"plan": "local", "status": "active"})
        self.assertEqual(asgi_request(self.module.app, "POST", "/api/billing/checkout", {"plan": "local"}, cookie=self.cookie, csrf=self.user["csrf_token"])[0], 409)
        with patch.object(self.module.stripe.billing_portal.Session, "create", return_value=SimpleNamespace(url="https://billing.stripe.com/test")) as portal:
            status, _, body = asgi_request(self.module.app, "POST", "/api/billing/portal", cookie=self.cookie, csrf=self.user["csrf_token"])
            self.assertEqual((status, body["url"]), (200, "https://billing.stripe.com/test"))
            self.assertEqual(portal.call_args.kwargs["customer"], "cus_test")
        event["type"] = "customer.subscription.deleted"
        event["created"] += 1
        event["data"]["object"]["status"] = "canceled"
        self.webhook(event)
        self.assertEqual(asgi_request(self.module.app, "GET", "/api/billing/status", cookie=self.cookie)[2]["billing"]["status"], "canceled")
