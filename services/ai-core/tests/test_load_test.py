import unittest

from scripts.load_test import Sample, build_report, nearest_rank


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


if __name__ == "__main__":
    unittest.main()
