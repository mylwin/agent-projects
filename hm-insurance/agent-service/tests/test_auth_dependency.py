import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
from starlette.requests import Request

from app.core.config import settings
from app.core.exceptions import TokenExpiredError, TokenInvalidError
from app.core.security import create_access_token, create_refresh_token
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.exceptions import (
    UnauthorizedError,
    UserInactiveError,
    UserSuspendedError,
)
from app.modules.auth.schemas import UserAuthData
from auth_support import make_user


def make_request(header: str | None = None) -> Request:
    headers = [] if header is None else [(b"authorization", header.encode())]
    return Request({"type": "http", "headers": headers})


def expired_token() -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": "42",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "type": "access",
        },
        settings.jwt.secret_key.get_secret_value(),
        algorithm="HS256",
    )


class CurrentUserTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_malformed_header_is_rejected(self):
        for header in (None, "Bearer", "Basic abc", "Token abc"):
            with self.subTest(header=header), self.assertRaises(UnauthorizedError):
                await get_current_user(make_request(header), AsyncMock())

    async def test_bad_tokens_are_rejected_before_database_query(self):
        for token in ("garbage", create_refresh_token("42"), expired_token()):
            with self.subTest(token=token), patch(
                "app.modules.auth.dependencies.UsersRepository"
            ) as repository:
                with self.assertRaises((TokenInvalidError, TokenExpiredError)):
                    await get_current_user(
                        make_request(f"Bearer {token}"), AsyncMock()
                    )
                repository.assert_not_called()

    async def test_valid_token_returns_current_user(self):
        with patch("app.modules.auth.dependencies.UsersRepository") as repository:
            repository.return_value.find_by_id = AsyncMock(
                return_value=make_user(display_name=None)
            )

            user = await get_current_user(
                make_request(f"Bearer {create_access_token('42')}"), AsyncMock()
            )

        self.assertEqual(
            user,
            UserAuthData(
                id=42,
                username="tester",
                email="tester@example.com",
                display_name="tester",
            ),
        )
        repository.return_value.find_by_id.assert_awaited_once_with(42)

    async def test_unknown_deleted_user_is_rejected(self):
        with patch("app.modules.auth.dependencies.UsersRepository") as repository:
            repository.return_value.find_by_id = AsyncMock(return_value=None)

            with self.assertRaises(TokenInvalidError):
                await get_current_user(
                    make_request(f"Bearer {create_access_token('42')}"), AsyncMock()
                )

    async def test_inactive_and_suspended_users_are_rejected(self):
        for status, error in (
            ("inactive", UserInactiveError),
            ("suspended", UserSuspendedError),
        ):
            with self.subTest(status=status), patch(
                "app.modules.auth.dependencies.UsersRepository"
            ) as repository:
                repository.return_value.find_by_id = AsyncMock(
                    return_value=make_user(status=status)
                )
                with self.assertRaises(error):
                    await get_current_user(
                        make_request(f"Bearer {create_access_token('42')}"), AsyncMock()
                    )


if __name__ == "__main__":
    unittest.main()
