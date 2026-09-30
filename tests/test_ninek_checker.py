"""Offline regression checks for the 9kBoss login response shape."""

import time
import unittest

from bot_src.modules import ninek_checker as checker


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, login_body, user_body=None):
        self.login_body = login_body
        self.user_body = user_body
        self.detail_headers = None
        self.detail_url = None

    def post(self, url, **kwargs):
        return FakeResponse(self.login_body)

    def get(self, url, **kwargs):
        self.detail_url = url
        self.detail_headers = kwargs["headers"]
        return FakeResponse(self.user_body)


class LoginResponseTests(unittest.TestCase):
    def setUp(self):
        checker._PENDING.clear()
        checker._TOKEN_CACHE.clear()
        self.user_id = 42
        self.email = "fixture@example.invalid"
        self.password = "test-only"

    def login(self, session):
        checker._PENDING[(self.user_id, self.email)] = {
            "session": session,
            "proxy": None,
            "password": self.password,
            "created": time.monotonic(),
        }
        return checker.complete_login(self.user_id, self.email, self.password, "AB12")

    def test_site_user_token_and_account_response(self):
        session = FakeSession(
            {"status": 0, "user": {"token": "fixture-token"}},
            {"status": 0, "user": {"balance": 12.5, "vipLevel": {"level": 3}}},
        )
        ok, result, error = self.login(session)
        self.assertTrue(ok, error)
        self.assertEqual(
            session.detail_url, "https://9kboss.com/api/auth/user_info"
        )
        self.assertEqual(session.detail_headers["Auth"], "fixture-token")
        self.assertEqual(result["user_info"]["balance"], 12.5)
        text, balance = checker.format_result(result, self.email)
        self.assertIn("VIP Level:</b> 3", text)
        self.assertEqual(balance, 12.5)

    def test_missing_token_is_not_a_verified_account(self):
        ok, _, error = self.login(FakeSession({"status": 0, "user": {}}))
        self.assertFalse(ok)
        self.assertIn("auth token", error)
        self.assertNotIn((self.user_id, self.email), checker._TOKEN_CACHE)

    def test_missing_balance_is_not_reported_as_zero(self):
        session = FakeSession(
            {"status": 0, "user": {"token": "fixture-token"}},
            {"status": 0, "user": {"vipLevel": {"level": 3}}},
        )
        ok, _, error = self.login(session)
        self.assertFalse(ok)
        self.assertIn("account details", error)
        self.assertNotIn((self.user_id, self.email), checker._TOKEN_CACHE)

    def test_zero_balance_is_valid(self):
        session = FakeSession(
            {"status": 0, "user": {"token": "fixture-token"}},
            {"status": 0, "user": {"balance": 0, "vipLevel": {"level": 1}}},
        )
        ok, result, error = self.login(session)
        self.assertTrue(ok, error)
        self.assertEqual(checker.format_result(result, self.email)[1], 0)


if __name__ == "__main__":
    unittest.main()