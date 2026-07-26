import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.http_metrics import HttpMetricsRegistry, http_metrics
from app.core.metric_alerts import evaluate_http_metrics
from config import settings
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

    def test_alert_evaluation_requires_enough_samples(self) -> None:
        registry = HttpMetricsRegistry()
        registry.start_request()
        registry.finish_request(method="GET", status_code=500, duration_ms=6000)

        report = evaluate_http_metrics(
            registry.snapshot(),
            minimum_samples=20,
            p95_warning_ms=3000,
            p95_critical_ms=5000,
            error_rate_warning_percent=1,
            error_rate_critical_percent=5,
            in_flight_warning=20,
            in_flight_critical=50,
        )

        self.assertFalse(report.evaluated)
        self.assertEqual(report.status, "healthy")
        self.assertEqual(report.alerts, [])

    def test_alert_evaluation_reports_critical_latency_and_error_rate(self) -> None:
        registry = HttpMetricsRegistry()
        for index in range(20):
            registry.start_request()
            registry.finish_request(
                method="GET",
                status_code=500 if index < 2 else 200,
                duration_ms=6000 if index >= 18 else 100,
            )

        report = evaluate_http_metrics(
            registry.snapshot(),
            minimum_samples=20,
            p95_warning_ms=3000,
            p95_critical_ms=5000,
            error_rate_warning_percent=1,
            error_rate_critical_percent=5,
            in_flight_warning=20,
            in_flight_critical=50,
        )

        self.assertTrue(report.evaluated)
        self.assertEqual(report.status, "critical")
        self.assertEqual(report.server_error_rate_percent, 10)
        self.assertEqual(
            {alert.code for alert in report.alerts},
            {"HTTP_P95_LATENCY_HIGH", "HTTP_SERVER_ERROR_RATE_HIGH"},
        )


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

    def test_scrape_endpoint_remains_available_when_api_auth_is_enabled(self) -> None:
        self.client.get("/health")

        with patch.object(settings, "API_AUTH_ENABLED", True):
            admin_response = self.client.get("/api/v1/metrics/http")
            scrape_response = self.client.get("/metrics")

        self.assertEqual(admin_response.status_code, 401)
        self.assertEqual(scrape_response.status_code, 200)
        self.assertNotIn("request_body", scrape_response.text)

    def test_alert_endpoint_returns_not_evaluated_for_small_sample(self) -> None:
        self.client.get("/health")

        response = self.client.get("/api/v1/metrics/alerts")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "healthy")
        self.assertFalse(payload["evaluated"])
        self.assertEqual(payload["sample_size"], 1)


if __name__ == "__main__":
    unittest.main()
