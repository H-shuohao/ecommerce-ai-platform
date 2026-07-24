import unittest

from fastapi.testclient import TestClient

from main import app


class ApiObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_response_contains_generated_request_id(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["X-Request-ID"])

    def test_valid_client_request_id_is_preserved(self) -> None:
        response = self.client.get(
            "/health",
            headers={"X-Request-ID": "interview-demo-001"},
        )

        self.assertEqual(response.headers["X-Request-ID"], "interview-demo-001")

    def test_not_found_uses_standard_error_envelope(self) -> None:
        response = self.client.get(
            "/api/v1/products/P9999",
            headers={"X-Request-ID": "missing-product-001"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "商品不存在")
        self.assertEqual(
            response.json()["error"],
            {
                "code": "RESOURCE_NOT_FOUND",
                "message": "商品不存在",
                "request_id": "missing-product-001",
            },
        )

    def test_validation_error_contains_traceable_error(self) -> None:
        response = self.client.post(
            "/api/v1/agents/presales/chat",
            json={"question": ""},
            headers={"X-Request-ID": "validation-001"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(
            response.json()["error"]["request_id"],
            "validation-001",
        )
