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
from database import Database
from main import app
from services.auth_user_repository import AuthUserRepository


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
        self.database = Database(":memory:")
        self.repository = AuthUserRepository(self.database)
        self.repository_patcher = patch(
            "app.api.auth.auth_user_repository",
            self.repository,
        )
        self.security_repository_patcher = patch(
            "app.core.security.auth_user_repository",
            self.repository,
        )
        self.repository_patcher.start()
        self.security_repository_patcher.start()
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
            "JWT_REFRESH_EXPIRES_DAYS": 7,
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

    def tearDown(self) -> None:
        self.security_repository_patcher.stop()
        self.repository_patcher.stop()
        self.database.connection.close()

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

    def test_admin_creates_database_user_and_login_is_audited(self) -> None:
        database_only_settings = {
            **self.auth_settings,
            "AUTH_USERS_JSON": "[]",
        }
        with patch.multiple(
            "app.core.security.settings",
            **database_only_settings,
        ):
            created = self.client.post(
                "/api/v1/auth/users",
                headers={"X-API-Key": "admin-test-key"},
                json={
                    "username": "service-user",
                    "password": "database-password",
                    "role": "service",
                },
            )
            login = self.client.post(
                "/api/v1/auth/login",
                json={
                    "username": "service-user",
                    "password": "database-password",
                },
            )
            failed_login = self.client.post(
                "/api/v1/auth/login",
                json={
                    "username": "service-user",
                    "password": "wrong-password",
                },
            )
            audits = self.client.get(
                "/api/v1/auth/login-audits",
                headers={"X-API-Key": "admin-test-key"},
            )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["role"], "service")
        self.assertNotIn("password", created.json())
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["role"], "service")
        self.assertEqual(failed_login.status_code, 401)
        self.assertEqual(audits.status_code, 200)
        self.assertEqual(len(audits.json()), 2)
        self.assertEqual(
            {item["success"] for item in audits.json()},
            {True, False},
        )

    def test_duplicate_database_username_returns_conflict(self) -> None:
        with patch.multiple("app.core.security.settings", **self.auth_settings):
            request = {
                "username": "duplicate-user",
                "password": "database-password",
                "role": "viewer",
            }
            first = self.client.post(
                "/api/v1/auth/users",
                headers={"X-API-Key": "admin-test-key"},
                json=request,
            )
            second = self.client.post(
                "/api/v1/auth/users",
                headers={"X-API-Key": "admin-test-key"},
                json=request,
            )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"], "用户名已存在")

    def test_refresh_and_account_disable_invalidate_tokens(self) -> None:
        database_only_settings = {**self.auth_settings, "AUTH_USERS_JSON": "[]"}
        with patch.multiple(
            "app.core.security.settings",
            **database_only_settings,
        ):
            self.client.post(
                "/api/v1/auth/users",
                headers={"X-API-Key": "admin-test-key"},
                json={
                    "username": "managed-user",
                    "password": "database-password",
                    "role": "viewer",
                },
            )
            login = self.client.post(
                "/api/v1/auth/login",
                json={
                    "username": "managed-user",
                    "password": "database-password",
                },
            )
            tokens = login.json()
            refreshed = self.client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": tokens["refresh_token"]},
            )
            disabled = self.client.patch(
                "/api/v1/auth/users/managed-user/status",
                headers={"X-API-Key": "admin-test-key"},
                json={"is_active": False},
            )
            protected = self.client.get(
                "/api/v1/products",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            rejected_refresh = self.client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": tokens["refresh_token"]},
            )

        self.assertEqual(login.status_code, 200)
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.json()["is_active"])
        self.assertEqual(protected.status_code, 401)
        self.assertEqual(rejected_refresh.status_code, 401)

    def test_change_password_invalidates_old_token_and_password(self) -> None:
        database_only_settings = {**self.auth_settings, "AUTH_USERS_JSON": "[]"}
        with patch.multiple(
            "app.core.security.settings",
            **database_only_settings,
        ):
            self.client.post(
                "/api/v1/auth/users",
                headers={"X-API-Key": "admin-test-key"},
                json={
                    "username": "password-user",
                    "password": "old-password",
                    "role": "viewer",
                },
            )
            login = self.client.post(
                "/api/v1/auth/login",
                json={"username": "password-user", "password": "old-password"},
            )
            old_access_token = login.json()["access_token"]
            changed = self.client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {old_access_token}"},
                json={
                    "current_password": "old-password",
                    "new_password": "new-password",
                },
            )
            old_token_result = self.client.get(
                "/api/v1/products",
                headers={"Authorization": f"Bearer {old_access_token}"},
            )
            old_login = self.client.post(
                "/api/v1/auth/login",
                json={"username": "password-user", "password": "old-password"},
            )
            new_login = self.client.post(
                "/api/v1/auth/login",
                json={"username": "password-user", "password": "new-password"},
            )

        self.assertEqual(changed.status_code, 204)
        self.assertEqual(old_token_result.status_code, 401)
        self.assertEqual(old_login.status_code, 401)
        self.assertEqual(new_login.status_code, 200)


if __name__ == "__main__":
    unittest.main()
