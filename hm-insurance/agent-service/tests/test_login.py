import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.exception_handlers import handle_request_validation_error
from app.core.exceptions import ApplicationError
from app.core.security import decode_access_token, hash_password
from app.main import handle_exception
from app.modules.auth.models import Users
from app.modules.auth.repository import UsersRepository
from app.modules.auth.router import get_user_service, router
from app.modules.auth.service import UsersService


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hashed_password = hash_password("pass123")

    def setUp(self):
        self.session = AsyncMock()
        self.service = UsersService(self.session)
        self.service.repository = AsyncMock(spec=UsersRepository)
        self.user = Users(
            id=42, username="tester", email="tester@example.com",
            password_hash=self.hashed_password, display_name="测试用户", status="active",
        )
        self.service.repository.find_by_username_or_email.return_value = self.user
        app = FastAPI()
        app.include_router(router)
        app.exception_handler(ApplicationError)(handle_exception)
        app.exception_handler(RequestValidationError)(handle_request_validation_error)
        app.dependency_overrides[get_user_service] = lambda: self.service
        self.client = TestClient(app)
        self.payload = {"username": " tester ", "password": "pass123"}

    def test_active_user_can_login_and_receives_token(self):
        response = self.client.post("/api/v1/auth/login", json=self.payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(decode_access_token(data["access_token"])["sub"], "42")
        self.assertEqual(data["user"]["id"], 42)
        self.assertEqual(data["user"]["display_name"], "测试用户")
        self.assertNotIn("password", response.text)
        self.service.repository.find_by_username_or_email.assert_awaited_once_with("tester")
        self.session.commit.assert_not_awaited()
        self.session.flush.assert_not_awaited()

    def test_user_existence_and_status_are_checked_before_password(self):
        for state, status_code, code, message in (
            (None, 401, "USER_NOT_FOUND", "用户不存在"),
            ("inactive", 403, "USER_INACTIVE", "用户尚未激活"),
            ("suspended", 403, "USER_SUSPENDED", "用户已被封禁"),
        ):
            with self.subTest(state=state):
                self.user.status = state
                self.service.repository.find_by_username_or_email.return_value = (
                    None if state is None else self.user
                )
                with patch("app.modules.auth.service.run_in_threadpool", new_callable=AsyncMock) as verify:
                    response = self.client.post("/api/v1/auth/login", json=self.payload)
                    verify.assert_not_awaited()
                self.assertEqual(response.status_code, status_code)
                self.assertEqual(response.json(), {"code": code, "message": message})

    def test_wrong_password_and_invalid_hash_do_not_issue_tokens(self):
        for hashed in (self.hashed_password, "invalid-hash"):
            with self.subTest(hashed=hashed):
                self.user.password_hash = hashed
                with patch("app.modules.auth.service.create_access_token") as create_token:
                    response = self.client.post(
                        "/api/v1/auth/login", json=self.payload | {"password": "wrong-password"}
                    )
                    create_token.assert_not_called()
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {
                    "code": "INVALID_CREDENTIALS", "message": "用户名或密码错误",
                })

    def test_invalid_request_uses_unified_error_response(self):
        response = self.client.post(
            "/api/v1/auth/login", json=self.payload | {"password": "123"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {
            "code": "REQUEST_VALIDATION_ERROR", "message": "密码至少需要6个字符",
        })
        self.service.repository.find_by_username_or_email.assert_not_awaited()


class LoginRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_lookup_only_matches_username(self):
        session = AsyncMock()
        user = MagicMock(spec=Users)
        session.scalar.return_value = user
        repository = UsersRepository(session)
        self.assertIs(await repository.find_by_username_or_email("tester"), user)
        statement = str(session.scalar.call_args.args[0])
        where_clause = statement.split("WHERE", 1)[1]
        self.assertIn("users.username =", where_clause)
        self.assertNotIn("users.email", where_clause)


if __name__ == "__main__":
    unittest.main()
