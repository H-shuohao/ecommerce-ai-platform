import unittest

from app.schemas.evaluations import EvaluationCaseResult, EvaluationReport
from database import Database
from services.evaluation_comparison_service import EvaluationComparisonService
from services.evaluation_run_repository import EvaluationRunRepository


def make_report(*, passed: bool, version: str = "v1", duration: float = 1000) -> EvaluationReport:
    return EvaluationReport(
        suite_version=version,
        total_cases=1,
        passed_cases=int(passed),
        failed_cases=int(not passed),
        pass_rate=100.0 if passed else 0.0,
        tool_selection_accuracy=100.0 if passed else 0.0,
        average_duration_ms=duration,
        results=[
            EvaluationCaseResult(
                id="inventory-p1002",
                question="查询库存",
                passed=passed,
                expected_tools=["check_inventory"],
                actual_tools=["check_inventory"] if passed else [],
                answer="结果" if passed else None,
                duration_ms=int(duration),
                failures=[] if passed else ["缺少预期工具调用"],
            )
        ],
    )


class EvaluationComparisonServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.repository = EvaluationRunRepository(self.db)
        self.service = EvaluationComparisonService(self.repository)

    def tearDown(self) -> None:
        self.db.connection.close()

    def test_detects_improved_case(self) -> None:
        baseline_id = self.repository.record(make_report(passed=False, duration=1500))
        candidate_id = self.repository.record(make_report(passed=True, duration=1200))

        comparison = self.service.compare(baseline_id, candidate_id)

        self.assertEqual(comparison.pass_rate_delta, 100.0)
        self.assertEqual(comparison.average_duration_ms_delta, -300.0)
        self.assertEqual(comparison.improved_cases, ["inventory-p1002"])
        self.assertEqual(comparison.regressed_cases, [])

    def test_rejects_different_suite_versions(self) -> None:
        baseline_id = self.repository.record(make_report(passed=True, version="v1"))
        candidate_id = self.repository.record(make_report(passed=True, version="v2"))

        with self.assertRaisesRegex(ValueError, "版本不同"):
            self.service.compare(baseline_id, candidate_id)


if __name__ == "__main__":
    unittest.main()
