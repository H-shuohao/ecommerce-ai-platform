import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


AUTH_SETTINGS = {
    "API_AUTH_ENABLED": True,
    "API_VIEWER_KEY": "viewer-test-key",
    "API_SERVICE_KEY": "service-test-key",
    "API_ADMIN_KEY": "admin-test-key",
}


class ApiSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch.multiple("app.core.security.settings", **AUTH_SETTINGS)
    def test_missing_api_key_is_rejected(self) -> None:
        response = self.client.get("/api/v1/products")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "缺少 API Key")

    @patch.multiple("app.core.security.settings", **AUTH_SETTINGS)
    def test_invalid_api_key_is_rejected(self) -> None:
        response = self.client.get(
            "/api/v1/products",
            headers={"X-API-Key": "wrong-key"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "API Key 无效")

    @patch.multiple("app.core.security.settings", **AUTH_SETTINGS)
    def test_viewer_can_read_commerce_data(self) -> None:
        response = self.client.get(
            "/api/v1/products",
            headers={"X-API-Key": "viewer-test-key"},
        )

        self.assertEqual(response.status_code, 200)

    @patch.multiple("app.core.security.settings", **AUTH_SETTINGS)
    def test_service_cannot_access_admin_data_platform(self) -> None:
        response = self.client.get(
            "/api/v1/data-platform/catalog",
            headers={"X-API-Key": "service-test-key"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "当前身份没有访问该接口的权限",
        )

    @patch.multiple("app.core.security.settings", **AUTH_SETTINGS)
    def test_admin_can_access_data_platform(self) -> None:
        response = self.client.get(
            "/api/v1/data-platform/catalog",
            headers={"X-API-Key": "admin-test-key"},
        )

        self.assertEqual(response.status_code, 200)

    @patch.multiple("app.core.security.settings", **AUTH_SETTINGS)
    def test_mcp_rejects_missing_api_key(self) -> None:
        response = self.client.get("/mcp")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "缺少 API Key")

    @patch.multiple("app.core.security.settings", **AUTH_SETTINGS)
    def test_mcp_rejects_viewer_role(self) -> None:
        response = self.client.get(
            "/mcp",
            headers={"X-API-Key": "viewer-test-key"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "当前身份没有访问 MCP 的权限")

    @patch("app.core.security.settings.API_AUTH_ENABLED", False)
    def test_local_development_remains_compatible(self) -> None:
        response = self.client.get("/api/v1/products")

        self.assertEqual(response.status_code, 200)
