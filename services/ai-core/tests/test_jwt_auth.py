import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.jwt_auth import (
    JwtValidationError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from main import app


class JwtPrimitiveTests(unittest.TestCase):
    def test_password_hash_round_trip(self) -> None:
        encoded = hash_password(
            "correct-password",
            iterations=1000,
            salt=b"0123456789abcdef",
        )

        self.assertTrue(verify_password("correct-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))

    def test_token_rejects_expiration_and_tampering(self) -> None:
        token, _ = create_access_token(
            username="viewer-user",
            role="viewer",
            secret="jwt-test-secret-with-enough-length",
            issuer="test-suite",
            expires_minutes=1,
            now=1000,
        )

        payload = decode_access_token(
            token,
            secret="jwt-test-secret-with-enough-length",
            issuer="test-suite",
            now=1059,
        )
        self.assertEqual(payload["sub"], "viewer-user")
        with self.assertRaises(JwtValidationError):
            decode_access_token(
                token,
                secret="jwt-test-secret-with-enough-length",
                issuer="test-suite",
                now=1060,
            )
        with self.assertRaises(JwtValidationError):
            decode_access_token(
                token + "x",
                secret="jwt-test-secret-with-enough-length",
                issuer="test-suite",
                now=1059,
            )
        with self.assertRaises(JwtValidationError):
            decode_access_token(
                "not-a.valid.jwt",
                secret="jwt-test-secret-with-enough-length",
                issuer="test-suite",
                now=1059,
            )


class JwtLoginApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.password_hash = hash_password(
            "demo-password",
            iterations=1000,
            salt=b"0123456789abcdef",
        )
        self.auth_settings = {
            "API_AUTH_ENABLED": True,
            "API_VIEWER_KEY": "viewer-test-key",
            "API_SERVICE_KEY": "service-test-key",
            "API_ADMIN_KEY": "admin-test-key",
            "JWT_AUTH_ENABLED": True,
            "JWT_SECRET": "jwt-test-secret-with-enough-length",
            "JWT_ISSUER": "test-suite",
            "JWT_EXPIRES_MINUTES": 60,
            "AUTH_USERS_JSON": json.dumps(
                [
                    {
                        "username": "viewer-user",
                        "password_hash": self.password_hash,
                        "role": "viewer",
                    }
                ]
            ),
        }

    def test_login_and_use_bearer_token(self) -> None:
        with patch.multiple("app.core.security.settings", **self.auth_settings):
            response = self.client.post(
                "/api/v1/auth/login",
                json={"username": "viewer-user", "password": "demo-password"},
            )
            payload = response.json()
            protected = self.client.get(
                "/api/v1/products",
                headers={"Authorization": f"Bearer {payload['access_token']}"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["token_type"], "bearer")
        self.assertEqual(payload["role"], "viewer")
        self.assertEqual(protected.status_code, 200)

    def test_login_rejects_wrong_password(self) -> None:
        with patch.multiple("app.core.security.settings", **self.auth_settings):
            response = self.client.post(
                "/api/v1/auth/login",
                json={"username": "viewer-user", "password": "wrong"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "用户名或密码错误")

    def test_viewer_jwt_cannot_access_admin_endpoint(self) -> None:
        with patch.multiple("app.core.security.settings", **self.auth_settings):
            login = self.client.post(
                "/api/v1/auth/login",
                json={"username": "viewer-user", "password": "demo-password"},
            )
            response = self.client.get(
                "/api/v1/data-platform/catalog",
                headers={
                    "Authorization": f"Bearer {login.json()['access_token']}"
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "当前身份没有访问该接口的权限",
        )


if __name__ == "__main__":
    unittest.main()
