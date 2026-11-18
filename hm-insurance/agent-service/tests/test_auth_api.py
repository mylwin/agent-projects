import unittest
from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import Users
from app.modules.auth.router import REFRESH_COOKIE_NAME
from app.modules.auth.schemas import UserAuthData
from auth_support import build_app, make_service, make_user

REGISTER_PAYLOAD = {
    "username": "tester",
    "email": "tester@example.com",
    "password": "pass123",
}


class AuthApiTestCase(unittest.TestCase):
    """认证接口测试共用的装配。"""

    def setUp(self):
        self.service = make_service()
        self.app = build_app(self.service)
        self.client = TestClient(self.app)


class RegisterTests(AuthApiTestCase):
    def test_register_returns_token_user_and_refresh_cookie(self):
        response = self.client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {"access_token", "token_type", "user"})
        self.assertEqual(body["token_type"], "Bearer")
        self.assertEqual(
            body["user"],
            {
                "id": 42,
                "username": "tester",
                "email": "tester@example.com",
                "display_name": "tester",
            },
        )
        self.assertEqual(decode_access_token(body["access_token"])["sub"], "42")
        self.assertNotIn("pass123", response.text)

        user = self.service.repository.add.call_args.args[0]
        self.assertNotEqual(user.password_hash, "pass123")
        self.assertTrue(verify_password("pass123", user.password_hash))

        cookie = response.headers["set-cookie"]
        self.assertIn(f"{REFRESH_COOKIE_NAME}=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Path=/api/v1/auth", cookie)
        self.assertIn(
            f"Max-Age={settings.jwt.refresh_token_expire_days * 86400}", cookie
        )
        self.assertEqual(
            decode_refresh_token(self.client.cookies[REFRESH_COOKIE_NAME])["sub"], "42"
        )

    def test_duplicate_username_or_email_returns_409(self):
        self.service.repository.find_by_username_or_email.return_value = make_user()

        response = self.client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"code": "USER_EXISTS", "message": "用户名或邮箱已被注册"},
        )
        self.service.repository.add.assert_not_awaited()

    def test_concurrent_duplicate_is_mapped_to_409(self):
        self.service.repository.add.side_effect = IntegrityError(
            "INSERT INTO users", {}, Exception("duplicate key")
        )

        response = self.client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "USER_EXISTS")

    def test_invalid_parameters_are_rejected_before_service_calls(self):
        cases = {
            "username 少于 3 个字符": ({"username": "ab"}, "用户名至少需要3个字符"),
            "username 超过 20 个字符": ({"username": "x" * 21}, "用户名最多允许20个字符"),
            "email 格式错误": ({"email": "not-an-email"}, "请输入有效的邮箱地址"),
            "密码少于 6 位": ({"password": "12345"}, "密码至少需要6个字符"),
            "密码超过 128 位": ({"password": "x" * 129}, "密码最多允许128个字符"),
        }
        for name, (changes, message) in cases.items():
            with self.subTest(name):
                response = self.client.post(
                    "/api/v1/auth/register", json=REGISTER_PAYLOAD | changes
                )
                self.assertEqual(response.status_code, 422, response.text)
                body = response.json()
                self.assertEqual(body["code"], "REQUEST_VALIDATION_ERROR")
                self.assertIn(message, body["message"])
                self.assertEqual(body["errors"][0]["message"], message)

        self.service.repository.find_by_username_or_email.assert_not_awaited()

    def test_missing_fields_report_each_field(self):
        response = self.client.post("/api/v1/auth/register", json={})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["errors"],
            [
                {"field": "username", "message": "用户名不能为空"},
                {"field": "email", "message": "邮箱不能为空"},
                {"field": "password", "message": "密码不能为空"},
            ],
        )

    def test_invalid_json_and_body_type_do_not_echo_input(self):
        invalid_json = self.client.post(
            "/api/v1/auth/register",
            content='{"password": "private-secret",',
            headers={"Content-Type": "application/json"},
        )
        wrong_body = self.client.post(
            "/api/v1/auth/register", json=["private-secret"]
        )

        self.assertEqual(invalid_json.status_code, 422)
        self.assertEqual(invalid_json.json()["message"], "请求体必须是有效的 JSON")
        self.assertEqual(wrong_body.status_code, 422)
        self.assertEqual(wrong_body.json()["message"], "请求体不符合要求")
        self.assertEqual(wrong_body.json()["errors"][0]["field"], "body")
        for response in (invalid_json, wrong_body):
            self.assertNotIn("private-secret", response.text)


class LoginTests(AuthApiTestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password("pass123")

    def setUp(self):
        super().setUp()
        self.user = make_user(password_hash=self.password_hash)
        self.service.repository.find_by_username_or_email.return_value = self.user

    def login(self, **changes):
        payload = {"username": "tester", "password": "pass123"} | changes
        return self.client.post("/api/v1/auth/login", json=payload)

    def test_active_user_can_login(self):
        response = self.login()

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["user"]["id"], 42)
        self.assertEqual(body["token_type"], "Bearer")
        self.assertEqual(decode_access_token(body["access_token"])["sub"], "42")
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.service.repository.find_by_username_or_email.assert_awaited_once_with(
            "tester", "tester"
        )

    def test_login_accepts_email_as_account(self):
        response = self.login(username="tester@example.com")

        self.assertEqual(response.status_code, 200)
        self.service.repository.find_by_username_or_email.assert_awaited_once_with(
            "tester@example.com", "tester@example.com"
        )

    def test_unknown_user_and_wrong_password_share_one_error(self):
        self.service.repository.find_by_username_or_email.return_value = None
        unknown = self.login()

        self.service.repository.find_by_username_or_email.return_value = self.user
        wrong = self.login(password="wrong-password")

        for response in (unknown, wrong):
            self.assertEqual(response.status_code, 401)
            self.assertEqual(
                response.json(),
                {"code": "INVALID_CREDENTIALS", "message": "用户名或密码错误"},
            )
            self.assertNotIn("set-cookie", response.headers)

    def test_inactive_and_suspended_users_get_403(self):
        for status, code, message in (
            ("inactive", "USER_INACTIVE", "用户尚未激活"),
            ("suspended", "USER_SUSPENDED", "用户已被封禁"),
        ):
            with self.subTest(status):
                self.user.status = status
                response = self.login()
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"code": code, "message": message})


class RefreshTests(AuthApiTestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password("pass123")

    def setUp(self):
        super().setUp()
        self.user = make_user(password_hash=self.password_hash)
        self.service.repository.find_by_id.return_value = self.user

    def set_refresh_cookie(self, token: str) -> None:
        self.client.cookies.set(
            REFRESH_COOKIE_NAME, token, domain="testserver.local", path="/api/v1/auth"
        )

    def test_refresh_rotates_token_and_returns_new_access_token(self):
        self.set_refresh_cookie(create_refresh_token("42"))
        old_cookie = self.client.cookies[REFRESH_COOKIE_NAME]

        response = self.client.post("/api/v1/auth/refresh")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(decode_access_token(body["access_token"])["sub"], "42")
        self.assertNotEqual(self.client.cookies[REFRESH_COOKIE_NAME], old_cookie)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.service.repository.find_by_id.assert_awaited_once_with(42)

    def test_missing_cookie_returns_401(self):
        response = self.client.post("/api/v1/auth/refresh")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "INVALID_REFRESH_TOKEN")
        self.assertNotIn("set-cookie", response.headers)
        self.service.repository.find_by_id.assert_not_awaited()

    def test_invalid_cookie_returns_401(self):
        for token in ("garbage", create_access_token("42"), create_refresh_token("0")):
            with self.subTest(token=token):
                self.set_refresh_cookie(token)
                response = self.client.post("/api/v1/auth/refresh")
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "INVALID_REFRESH_TOKEN")
        self.service.repository.find_by_id.assert_not_awaited()

    def test_deleted_user_returns_401(self):
        self.set_refresh_cookie(create_refresh_token("42"))
        self.service.repository.find_by_id.return_value = None

        response = self.client.post("/api/v1/auth/refresh")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "INVALID_REFRESH_TOKEN")
        self.assertNotIn("set-cookie", response.headers)

    def test_inactive_user_returns_403(self):
        self.set_refresh_cookie(create_refresh_token("42"))
        self.user.status = "inactive"

        response = self.client.post("/api/v1/auth/refresh")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "USER_INACTIVE")
        self.assertNotIn("set-cookie", response.headers)


class LogoutTests(AuthApiTestCase):
    def test_logout_clears_cookie_and_is_idempotent(self):
        self.client.cookies.set(
            REFRESH_COOKIE_NAME,
            create_refresh_token("42"),
            domain="testserver.local",
            path="/api/v1/auth",
        )

        for _ in range(2):
            response = self.client.post("/api/v1/auth/logout")
            self.assertEqual(response.status_code, 204)
            self.assertIn("Max-Age=0", response.headers["set-cookie"])

        self.assertNotIn(REFRESH_COOKIE_NAME, self.client.cookies)


class MeTests(AuthApiTestCase):
    def test_missing_token_returns_401(self):
        response = self.client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(), {"code": "UNAUTHORIZED", "message": "请先登录"}
        )

    def test_refresh_token_is_not_accepted_as_access_token(self):
        response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {create_refresh_token('42')}"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "TOKEN_INVALID")

    def test_expired_access_token_returns_token_expired(self):
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": "42",
                "iat": now - timedelta(hours=2),
                "exp": now - timedelta(hours=1),
                "type": "access",
            },
            settings.jwt.secret_key.get_secret_value(),
            algorithm="HS256",
        )

        response = self.client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "TOKEN_EXPIRED")

    def test_current_user_is_returned(self):
        user = UserAuthData(
            id=42, username="tester", email="tester@example.com", display_name="tester"
        )
        self.app.dependency_overrides[get_current_user] = lambda: user

        response = self.client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), user.model_dump())

    def test_display_name_falls_back_to_username(self):
        user: Users = make_user(display_name=None)
        self.assertEqual(UserAuthData.from_user(user).display_name, "tester")


if __name__ == "__main__":
    unittest.main()
