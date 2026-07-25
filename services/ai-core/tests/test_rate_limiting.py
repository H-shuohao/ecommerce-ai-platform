import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.rate_limiting import FixedWindowRateLimiter, rate_limiter
from main import app


class FixedWindowRateLimiterTests(unittest.TestCase):
    def test_window_resets_after_configured_seconds(self) -> None:
        limiter = FixedWindowRateLimiter()

        first = limiter.check("client", limit=1, window_seconds=10, now=100)
        blocked = limiter.check("client", limit=1, window_seconds=10, now=105)
        reset = limiter.check("client", limit=1, window_seconds=10, now=110)

        self.assertTrue(first.allowed)
        self.assertFalse(blocked.allowed)
        self.assertTrue(reset.allowed)


class ApiRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        rate_limiter.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        rate_limiter.clear()

    @patch.multiple(
        "app.core.rate_limiting.settings",
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_REQUESTS=2,
        RATE_LIMIT_WINDOW_SECONDS=60,
    )
    def test_api_returns_429_after_client_uses_quota(self) -> None:
        first = self.client.get("/api/v1/products")
        second = self.client.get("/api/v1/products")
        blocked = self.client.get("/api/v1/products")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers["X-RateLimit-Remaining"], "1")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.headers["X-RateLimit-Remaining"], "0")
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(
            blocked.json()["error"]["code"],
            "RATE_LIMIT_EXCEEDED",
        )
        self.assertEqual(blocked.headers["Retry-After"], "60")
        self.assertTrue(blocked.headers["X-Request-ID"])
        self.assertEqual(
            blocked.json()["error"]["request_id"],
            blocked.headers["X-Request-ID"],
        )

    @patch.multiple(
        "app.core.rate_limiting.settings",
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_REQUESTS=1,
        RATE_LIMIT_WINDOW_SECONDS=60,
    )
    def test_health_check_is_not_rate_limited(self) -> None:
        responses = [self.client.get("/health") for _ in range(3)]

        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertTrue(
            all("X-RateLimit-Limit" not in response.headers for response in responses)
        )


if __name__ == "__main__":
    unittest.main()
