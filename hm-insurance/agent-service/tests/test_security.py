import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt
from pydantic import SecretStr, ValidationError

from app.core.config import JWTSettings, settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.modules.auth.exceptions import TokenExpiredError, TokenInvalidError


class PasswordTests(unittest.TestCase):
    def test_password_round_trip_and_wrong_password(self):
        hashed = hash_password("测试密码-123")
        self.assertTrue(hashed.startswith("$argon2id$"))
        self.assertTrue(verify_password("测试密码-123", hashed))
        self.assertFalse(verify_password("wrong-password", hashed))

    def test_each_hash_uses_a_new_salt(self):
        self.assertNotEqual(hash_password("same"), hash_password("same"))

    def test_invalid_hash_is_rejected(self):
        for hashed in ("", "plain-text", "$argon2id$broken"):
            with self.subTest(hashed=hashed):
                self.assertFalse(verify_password("password", hashed))


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.key = "test-signing-secret-with-at-least-48-characters-for-hmac"
        patcher = patch.object(settings.jwt, "secret_key", SecretStr(self.key))
        patcher.start()
        self.addCleanup(patcher.stop)

    def signed_token(self, **overrides):
        now = datetime.now(UTC)
        payload = {"sub": "user-1", "iat": now, "exp": now + timedelta(minutes=5)}
        payload.update(overrides)
        return jwt.encode(payload, self.key, algorithm="HS256")

    def test_round_trip_and_default_expiration(self):
        user_id = uuid4()
        payload = decode_access_token(create_access_token(user_id))
        self.assertEqual(payload["sub"], str(user_id))
        self.assertEqual(
            payload["exp"] - payload["iat"],
            settings.jwt.access_token_expire_minutes * 60,
        )

    def test_custom_expiration(self):
        payload = decode_access_token(create_access_token("user-1", timedelta(minutes=5)))
        self.assertEqual(payload["exp"] - payload["iat"], 300)

    def test_expired_token_is_rejected(self):
        token = self.signed_token(exp=datetime.now(UTC) - timedelta(seconds=10))
        with self.assertRaises(TokenExpiredError):
            decode_access_token(token)

    def test_wrong_signature_and_algorithm_are_rejected(self):
        tokens = (
            jwt.encode({"sub": "user-1"}, "different-secret-which-is-long-enough", algorithm="HS256"),
            jwt.encode({"sub": "user-1"}, self.key, algorithm="HS384"),
            jwt.encode({"sub": "user-1"}, "", algorithm="none"),
            "malformed-token",
        )
        for token in tokens:
            with self.subTest(token=token), self.assertRaises(TokenInvalidError):
                decode_access_token(token)

    def test_required_claims_cannot_be_omitted(self):
        payload = decode_access_token(self.signed_token())
        for claim in ("sub", "iat", "exp"):
            incomplete = {key: value for key, value in payload.items() if key != claim}
            token = jwt.encode(incomplete, self.key, algorithm="HS256")
            with self.subTest(claim=claim), self.assertRaises(TokenInvalidError):
                decode_access_token(token)

    def test_invalid_subject_is_rejected(self):
        for subject in ("", " ", 123):
            with self.subTest(subject=subject), self.assertRaises(TokenInvalidError):
                decode_access_token(self.signed_token(sub=subject))

    def test_invalid_creation_parameters_are_rejected(self):
        for subject, lifetime in (("", None), (" ", None), ("user-1", timedelta(0))):
            with self.subTest(subject=subject, lifetime=lifetime), self.assertRaises(ValueError):
                create_access_token(subject, lifetime)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValidationError):
            JWTSettings(JWT_SECRET_KEY="too-short", _env_file=None)
        with self.assertRaises(ValidationError):
            JWTSettings(JWT_SECRET_KEY=self.key, JWT_ACCESS_TOKEN_EXPIRE_MINUTES=0)


if __name__ == "__main__":
    unittest.main()
