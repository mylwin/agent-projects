import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jwt
from pydantic import SecretStr, ValidationError

from app.core.config import JWTSettings, settings
from app.core.exceptions import (
    InvalidRefreshTokenError,
    TokenExpiredError,
    TokenInvalidError,
    TokenError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)


class PasswordTests(unittest.TestCase):
    def test_password_round_trip(self):
        hashed = hash_password("测试密码-123")
        self.assertTrue(hashed.startswith("$argon2id$"))
        self.assertTrue(verify_password("测试密码-123", hashed))
        self.assertFalse(verify_password("wrong-password", hashed))

    def test_each_hash_uses_a_new_salt(self):
        self.assertNotEqual(hash_password("same"), hash_password("same"))

    def test_broken_hash_is_rejected(self):
        for hashed in ("", "plain-text", "$argon2id$broken"):
            with self.subTest(hashed=hashed):
                self.assertFalse(verify_password("password", hashed))


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.key = "test-signing-secret-with-at-least-48-characters-for-hmac"
        patcher = patch.object(settings.jwt, "secret_key", SecretStr(self.key))
        patcher.start()
        self.addCleanup(patcher.stop)

    def signed(self, **overrides) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": "1",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "type": "access",
        }
        payload.update(overrides)
        return jwt.encode(payload, self.key, algorithm="HS256")

    def test_access_token_round_trip(self):
        payload = decode_access_token(create_access_token("42"))
        self.assertEqual(payload["sub"], "42")
        self.assertEqual(payload["type"], "access")
        self.assertEqual(
            payload["exp"] - payload["iat"],
            settings.jwt.access_token_expire_minutes * 60,
        )

    def test_refresh_token_round_trip(self):
        payload = decode_refresh_token(create_refresh_token("42"))
        self.assertEqual(payload["sub"], "42")
        self.assertEqual(payload["type"], "refresh")
        self.assertEqual(
            payload["exp"] - payload["iat"],
            settings.jwt.refresh_token_expire_days * 86400,
        )

    def test_expired_token_is_rejected(self):
        token = self.signed(exp=datetime.now(UTC) - timedelta(seconds=10))
        with self.assertRaises(TokenExpiredError):
            decode_access_token(token)

    def test_wrong_signature_algorithm_and_format_are_rejected(self):
        tokens = (
            jwt.encode({"sub": "1"}, "different-secret-which-is-long-enough", algorithm="HS256"),
            jwt.encode({"sub": "1"}, self.key, algorithm="HS384"),
            jwt.encode({"sub": "1"}, "", algorithm="none"),
            "malformed-token",
        )
        for token in tokens:
            with self.subTest(token=token), self.assertRaises(TokenInvalidError):
                decode_access_token(token)

    def test_required_claims_cannot_be_omitted(self):
        for claim in ("sub", "iat", "exp"):
            payload = {"sub": "1", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5)}
            del payload[claim]
            payload["type"] = "access"
            with self.subTest(claim=claim), self.assertRaises(TokenError):
                decode_access_token(jwt.encode(payload, self.key, algorithm="HS256"))

    def test_token_type_is_enforced(self):
        with self.assertRaises(TokenInvalidError):
            decode_access_token(create_refresh_token("42"))
        with self.assertRaises(InvalidRefreshTokenError):
            decode_refresh_token(create_access_token("42"))

    def test_refresh_token_requires_numeric_user_id(self):
        for subject in ("", " ", "not-a-number", "0", "-1", str(2**63)):
            token = jwt.encode(
                {
                    "sub": subject,
                    "iat": datetime.now(UTC),
                    "exp": datetime.now(UTC) + timedelta(days=1),
                    "type": "refresh",
                    "jti": "test",
                },
                self.key,
                algorithm="HS256",
            )
            with self.subTest(subject=subject), self.assertRaises(InvalidRefreshTokenError):
                decode_refresh_token(token)

    def test_access_token_requires_numeric_user_id(self):
        with self.assertRaises(TokenInvalidError):
            decode_access_token(self.signed(type="access", sub="user-1"))


class JWTConfigTests(unittest.TestCase):
    def test_secret_and_lifetime_are_validated(self):
        with self.assertRaises(ValidationError):
            JWTSettings(JWT_SECRET_KEY="too-short", _env_file=None)
        with self.assertRaises(ValidationError):
            JWTSettings(
                JWT_SECRET_KEY="x" * 48,
                JWT_ACCESS_TOKEN_EXPIRE_MINUTES=0,
                _env_file=None,
            )


if __name__ == "__main__":
    unittest.main()
