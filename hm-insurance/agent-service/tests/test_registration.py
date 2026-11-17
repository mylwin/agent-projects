import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ApplicationError
from app.core.exception_handlers import handle_request_validation_error
from app.core.security import decode_access_token, verify_password
from app.modules.auth.exceptions import UserAlreadyExistError
from app.modules.auth.repository import UsersRepository
from app.modules.auth.router import get_user_service, router
from app.modules.auth.schemas import UserRegisterRequest
from app.modules.auth.service import UsersService


def make_service():
    session = MagicMock()
    session.begin.return_value = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    service = UsersService(session)
    service.repository = AsyncMock(spec=UsersRepository)
    service.repository.find_by_username_or_email.return_value = None

    async def add(user):
        user.id = 42

    service.repository.add.side_effect = add
    return service


class UniqueViolation(Exception):
    def __init__(self, constraint: str):
        super().__init__("unique violation")
        self.constraint_name = constraint


class DatabaseError(Exception):
    sqlstate = "23505"


def unique_violation(constraint: str) -> IntegrityError:
    cause = UniqueViolation(constraint)
    original = DatabaseError("database error")
    original.__cause__ = cause
    return IntegrityError("INSERT INTO users", {}, original)


class RegistrationServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = make_service()
        self.request = UserRegisterRequest(
            username="tester", email="tester@example.com", password="pass123"
        )

    async def test_registration_hashes_password_and_returns_user_token(self):
        response = await self.service.register(self.request)
        user = self.service.repository.add.call_args.args[0]
        self.assertNotEqual(user.password_hash, self.request.password)
        self.assertTrue(verify_password(self.request.password, user.password_hash))
        self.assertEqual(user.display_name, self.request.username)
        self.assertEqual(user.status, "active")
        self.service.session.flush.assert_awaited_once()
        self.service.session.refresh.assert_awaited_once_with(user)
        self.assertEqual(response.user.id, 42)
        self.assertEqual(decode_access_token(response.access_token)["sub"], "42")
        self.assertNotIn("password", response.model_dump_json())
        self.service.session.begin.return_value.__aexit__.assert_awaited_once_with(
            None, None, None
        )

    async def test_existing_username_or_email_is_rejected_before_insert(self):
        self.service.repository.find_by_username_or_email.return_value = MagicMock()
        with self.assertRaises(UserAlreadyExistError):
            await self.service.register(self.request)
        self.service.repository.add.assert_not_awaited()
        self.service.repository.find_by_username_or_email.assert_awaited_once_with(
            "tester", "tester@example.com"
        )

    async def test_concurrent_registration_conflicts_roll_back(self):
        for constraint in ("users_username_key", "users_email_key"):
            with self.subTest(constraint=constraint):
                service = make_service()
                service.session.flush.side_effect = unique_violation(constraint)
                with self.assertRaises(UserAlreadyExistError):
                    await service.register(self.request)
                exit_args = service.session.begin.return_value.__aexit__.call_args.args
                self.assertIs(exit_args[0], IntegrityError)

    async def test_other_database_errors_are_not_reported_as_duplicate_users(self):
        error = unique_violation("users_pkey")
        self.service.session.flush.side_effect = error
        with self.assertRaises(IntegrityError):
            await self.service.register(self.request)


class RegistrationEndpointTests(unittest.TestCase):
    def setUp(self):
        self.service = make_service()
        app = FastAPI()
        app.exception_handler(RequestValidationError)(handle_request_validation_error)
        app.include_router(router)
        app.dependency_overrides[get_user_service] = lambda: self.service

        @app.exception_handler(ApplicationError)
        async def handle_error(request: Request, exc: ApplicationError):
            return JSONResponse(
                status_code=exc.status_code,
                content={"code": exc.code, "message": exc.message},
            )

        self.client = TestClient(app)
        self.payload = {
            "username": " tester ",
            "email": " tester@example.com ",
            "password": "pass123",
        }

    def test_register_endpoint_returns_safe_user_data(self):
        response = self.client.post("/api/v1/auth/register", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["user"], {
            "id": 42, "username": "tester", "email": "tester@example.com",
            "display_name": "tester",
        })
        self.assertEqual(data["token_type"], "Bearer")
        self.assertIn("refresh_token=", response.headers["set-cookie"])
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertEqual(decode_access_token(data["access_token"])["sub"], "42")
        self.assertNotIn("password", response.text)

    def test_duplicate_registration_returns_409(self):
        self.service.repository.find_by_username_or_email.return_value = MagicMock()
        response = self.client.post("/api/v1/auth/register", json=self.payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "USER_EXISTS")

    def test_invalid_parameters_are_rejected_before_service_calls(self):
        for changes in (
            {"username": "  "}, {"username": "x" * 21},
            {"email": "invalid-email"}, {"email": "a b@example.com"},
            {"password": "short"}, {"password": "x" * 21},
        ):
            with self.subTest(changes=changes):
                response = self.client.post(
                    "/api/v1/auth/register", json=self.payload | changes
                )
                self.assertEqual(response.status_code, 422)
        self.service.repository.find_by_username_or_email.assert_not_awaited()

    def test_validation_errors_are_chinese_and_do_not_echo_input(self):
        response = self.client.post(
            "/api/v1/auth/register",
            json=self.payload | {"email": "2232802210", "password": "123"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "请输入有效的邮箱地址；密码至少需要6个字符",
        })
        self.assertNotIn("2232802210", response.text)
        self.assertNotIn("123", response.text)

    def test_missing_fields_have_chinese_messages(self):
        response = self.client.post("/api/v1/auth/register", json={})
        self.assertEqual(response.json(), {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "用户名不能为空；邮箱不能为空；密码不能为空",
        })

    def test_invalid_json_does_not_echo_request_body(self):
        response = self.client.post(
            "/api/v1/auth/register", content='{"password":"private-secret",',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "请求体必须是有效的 JSON",
        })
        self.assertNotIn("private-secret", response.text)

    def test_invalid_body_type_uses_safe_fallback_message(self):
        response = self.client.post("/api/v1/auth/register", json=["private-secret"])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "请求体不符合要求",
        })
        self.assertNotIn("private-secret", response.text)


class UsersRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_insert_only_adds_user_to_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        repository = UsersRepository(session)
        user = MagicMock()
        await repository.add(user)
        session.add.assert_called_once_with(user)
        session.flush.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_duplicate_lookup_checks_username_and_email(self):
        session = AsyncMock()
        repository = UsersRepository(session)
        user = MagicMock()
        session.scalar.return_value = user
        self.assertIs(
            await repository.find_by_username_or_email("tester", "a@b.com"), user
        )
        statement = str(session.scalar.call_args.args[0])
        self.assertIn("users.username =", statement)
        self.assertIn(" OR users.email =", statement)
        session.scalar.return_value = None
        self.assertIsNone(
            await repository.find_by_username_or_email("tester", "a@b.com")
        )


if __name__ == "__main__":
    unittest.main()
