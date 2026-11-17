import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.core.security import (
    create_access_token, create_refresh_token, decode_access_token,
    decode_refresh_token, hash_password,
)
from app.main import handle_exception
from app.modules.auth.exceptions import TokenInvalidError
from app.modules.auth.models import Users
from app.modules.auth.repository import UsersRepository
from app.modules.auth.router import REFRESH_COOKIE_NAME, get_user_service, router
from app.modules.auth.service import UsersService


class RefreshLogoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hashed_password = hash_password("pass123")

    def setUp(self):
        secure_patch = patch.object(settings.jwt, "refresh_cookie_secure", False)
        secure_patch.start()
        self.addCleanup(secure_patch.stop)
        self.service = UsersService(AsyncMock())
        self.service.repository = AsyncMock(spec=UsersRepository)
        self.user = Users(
            id=42, username="tester", email="tester@example.com",
            display_name="测试用户", password_hash=self.hashed_password, status="active",
        )
        self.service.repository.find_by_id.return_value = self.user
        self.service.repository.find_by_username_or_email.return_value = self.user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.exception_handler(ApplicationError)(handle_exception)
        self.app.dependency_overrides[get_user_service] = lambda: self.service
        self.client = TestClient(self.app)

    def login(self, client=None):
        return (client or self.client).post(
            "/api/v1/auth/login", json={"username": "tester", "password": "pass123"}
        )

    def set_token(self, token):
        self.client.cookies.set(
            REFRESH_COOKIE_NAME, token, domain="testserver.local", path="/api/v1/auth"
        )

    def test_login_refresh_logout_browser_flow(self):
        login = self.login()
        self.assertEqual(login.status_code, 200)
        first_cookie = self.client.cookies[REFRESH_COOKIE_NAME]
        self.assertEqual(decode_refresh_token(first_cookie)["sub"], "42")
        self.assertNotIn(first_cookie, login.text)

        refreshed = self.client.post("/api/v1/auth/refresh")
        self.assertEqual(refreshed.status_code, 200)
        body = refreshed.json()
        self.assertEqual(set(body), {"access_token", "token_type", "user"})
        self.assertEqual(body["token_type"], "Bearer")
        self.assertEqual(body["user"]["id"], 42)
        self.assertEqual(decode_access_token(body["access_token"])["sub"], "42")
        self.assertNotEqual(body["access_token"], login.json()["access_token"])
        self.assertNotEqual(self.client.cookies[REFRESH_COOKIE_NAME], first_cookie)
        cookie = refreshed.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Path=/api/v1/auth", cookie)
        self.assertIn(f"Max-Age={settings.jwt.refresh_token_expire_days * 86400}", cookie)
        self.service.repository.find_by_id.assert_awaited_once_with(42)

        logout = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout.json(), {"ok": True})
        self.assertEqual(logout.status_code, 200)
        self.assertIn("Max-Age=0", logout.headers["set-cookie"])
        self.assertNotIn(REFRESH_COOKIE_NAME, self.client.cookies)
        self.assertEqual(self.client.post("/api/v1/auth/refresh").status_code, 401)

    def test_missing_refresh_cookie_returns_401(self):
        response = self.client.post("/api/v1/auth/refresh")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {
            "code": "INVALID_REFRESH_TOKEN",
            "message": "Refresh token is invalid or expired",
        })
        self.service.repository.find_by_id.assert_not_awaited()

    def test_refresh_extends_cookie_lifetime_without_valid_access_token(self):
        now = datetime.now(UTC)
        old_payload = {
            "sub": "42", "type": "refresh", "jti": "old-refresh-token",
            "iat": now - timedelta(days=1), "exp": now + timedelta(hours=1),
        }
        key = settings.jwt.secret_key.get_secret_value()
        self.set_token(jwt.encode(old_payload, key, algorithm="HS256"))
        expired_access = jwt.encode({
            "sub": "42", "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1), "type": "access",
        }, key, algorithm="HS256")
        response = self.client.post(
            "/api/v1/auth/refresh", headers={"Authorization": f"Bearer {expired_access}"}
        )
        self.assertEqual(response.status_code, 200)
        new_payload = decode_refresh_token(self.client.cookies[REFRESH_COOKIE_NAME])
        self.assertGreater(new_payload["exp"], int(old_payload["exp"].timestamp()))
        self.assertEqual(
            new_payload["exp"] - new_payload["iat"],
            settings.jwt.refresh_token_expire_days * 86400,
        )
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_invalid_and_expired_tokens_are_rejected(self):
        now = datetime.now(UTC)
        payload = {"sub": "42", "type": "refresh", "jti": "test", "iat": now}
        expired = jwt.encode(
            payload | {"exp": now - timedelta(seconds=10)},
            settings.jwt.secret_key.get_secret_value(), algorithm="HS256",
        )
        forged = jwt.encode(
            payload | {"exp": now + timedelta(days=1)},
            "wrong-secret-that-is-at-least-32-characters", algorithm="HS256",
        )
        unsigned = jwt.encode(
            payload | {"exp": now + timedelta(days=1)}, "", algorithm="none"
        )
        for token in ("", "malformed", expired, forged, unsigned, create_access_token("42")):
            with self.subTest(token=token):
                self.set_token(token)
                response = self.client.post("/api/v1/auth/refresh")
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "INVALID_REFRESH_TOKEN")
                self.assertNotIn("set-cookie", response.headers)
        self.service.repository.find_by_id.assert_not_awaited()

    def test_refresh_token_cannot_be_used_as_access_token(self):
        with self.assertRaises(TokenInvalidError):
            decode_access_token(create_refresh_token(42))

    def test_invalid_user_ids_are_rejected_before_database_query(self):
        for subject in ("not-a-number", "0", "-1", str(2**63)):
            with self.subTest(subject=subject):
                self.set_token(create_refresh_token(subject))
                response = self.client.post("/api/v1/auth/refresh")
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "INVALID_REFRESH_TOKEN")
        self.service.repository.find_by_id.assert_not_awaited()

    def test_deleted_user_returns_404(self):
        self.set_token(create_refresh_token(42))
        self.service.repository.find_by_id.return_value = None
        response = self.client.post("/api/v1/auth/refresh")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"code": "USER_NOT_FOUND", "message": "用户不存在"})
        self.assertNotIn("set-cookie", response.headers)

    def test_inactive_and_suspended_users_return_400(self):
        for state in ("inactive", "suspended"):
            with self.subTest(state=state):
                self.user.status = state
                self.set_token(create_refresh_token(42))
                response = self.client.post("/api/v1/auth/refresh")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {
                    "code": "INACTIVE_USER", "message": "用户已被停用",
                })
                self.assertNotIn("set-cookie", response.headers)

    def test_secure_cookie_can_be_enabled_for_https(self):
        with patch.object(settings.jwt, "refresh_cookie_secure", True):
            client = TestClient(self.app, base_url="https://testserver")
            response = self.login(client)
            self.assertIn("Secure", response.headers["set-cookie"])
            self.assertEqual(client.post("/api/v1/auth/refresh").status_code, 200)
            logout = client.post("/api/v1/auth/logout")
            self.assertIn("Secure", logout.headers["set-cookie"])
            self.assertNotIn(REFRESH_COOKIE_NAME, client.cookies)

    def test_logout_without_cookie_is_idempotent_and_needs_no_database(self):
        self.app.dependency_overrides[get_user_service] = lambda: self.fail("无需访问数据库")
        for _ in range(2):
            response = self.client.post("/api/v1/auth/logout")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
