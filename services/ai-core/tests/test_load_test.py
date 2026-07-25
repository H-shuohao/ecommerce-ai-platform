import unittest

import httpx

from scripts.load_test import (
    Sample,
    _validate_agent_response,
    build_report,
    nearest_rank,
)


class LoadTestMetricsTests(unittest.TestCase):
    def test_nearest_rank_percentiles(self) -> None:
        values = [10, 20, 30, 40, 50]

        self.assertEqual(nearest_rank(values, 0.50), 30)
        self.assertEqual(nearest_rank(values, 0.95), 50)

    def test_report_counts_failures_and_status_codes(self) -> None:
        report = build_report(
            profile="commerce",
            target_url="http://test",
            total_requests=4,
            concurrency=2,
            samples=[
                Sample(status_code=200, duration_ms=10),
                Sample(status_code=200, duration_ms=20),
                Sample(status_code=429, duration_ms=30),
                Sample(status_code=None, duration_ms=40, error="ReadTimeout"),
            ],
            wall_time_seconds=0.5,
        )

        self.assertEqual(report.successful_requests, 2)
        self.assertEqual(report.failed_requests, 2)
        self.assertEqual(report.success_rate, 50)
        self.assertEqual(report.throughput_rps, 8)
        self.assertEqual(report.status_codes, {"200": 2, "429": 1})
        self.assertEqual(report.errors, {"ReadTimeout": 1})

    def test_agent_response_requires_expected_tool(self) -> None:
        valid = httpx.Response(
            200,
            json={
                "answer": "P1002 当前无库存。",
                "tool_calls": [{"tool": "check_inventory"}],
            },
        )
        invalid = httpx.Response(
            200,
            json={
                "answer": "我猜测当前有库存。",
                "tool_calls": [],
            },
        )

        self.assertIsNone(_validate_agent_response(valid, 0))
        self.assertEqual(
            _validate_agent_response(invalid, 0),
            "ExpectedToolNotCalled:check_inventory",
        )

    def test_report_treats_application_validation_error_as_failure(self) -> None:
        report = build_report(
            profile="agent",
            target_url="http://test",
            total_requests=1,
            concurrency=1,
            samples=[
                Sample(
                    status_code=200,
                    duration_ms=100,
                    error="ExpectedToolNotCalled:check_inventory",
                )
            ],
            wall_time_seconds=0.1,
        )

        self.assertEqual(report.successful_requests, 0)
        self.assertEqual(report.failed_requests, 1)
        self.assertEqual(
            report.errors,
            {"ExpectedToolNotCalled:check_inventory": 1},
        )


if __name__ == "__main__":
    unittest.main()
