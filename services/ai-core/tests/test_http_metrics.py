import unittest

from fastapi.testclient import TestClient

from app.core.http_metrics import HttpMetricsRegistry, http_metrics
from main import app


class HttpMetricsRegistryTests(unittest.TestCase):
    def test_snapshot_calculates_status_and_latency_metrics(self) -> None:
        registry = HttpMetricsRegistry()
        registry.start_request()
        registry.finish_request(method="GET", status_code=200, duration_ms=10)
        registry.start_request()
        registry.finish_request(method="POST", status_code=404, duration_ms=30)

        snapshot = registry.snapshot()

        self.assertEqual(snapshot.total_requests, 2)
        self.assertEqual(snapshot.success_requests, 1)
        self.assertEqual(snapshot.client_error_requests, 1)
        self.assertEqual(snapshot.server_error_requests, 0)
        self.assertEqual(snapshot.average_duration_ms, 20)
        self.assertEqual(snapshot.p95_duration_ms, 30)


class HttpMetricsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        http_metrics.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        http_metrics.clear()

    def test_json_metrics_endpoint_reports_completed_requests(self) -> None:
        self.client.get("/health")
        self.client.get("/api/v1/products")

        response = self.client.get("/api/v1/metrics/http")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["total_requests"], 2)
        self.assertEqual(payload["success_requests"], 2)
        self.assertEqual(payload["status_codes"], {"200": 2})
        self.assertGreaterEqual(payload["p95_duration_ms"], 0)

    def test_prometheus_endpoint_uses_text_exposition(self) -> None:
        self.client.get("/health")

        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'ai_core_http_requests_total{status_code="200"} 1',
            response.text,
        )
        self.assertIn("ai_core_http_requests_in_flight", response.text)


if __name__ == "__main__":
    unittest.main()
