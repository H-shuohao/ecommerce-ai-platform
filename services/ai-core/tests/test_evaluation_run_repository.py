import unittest

from app.schemas.evaluations import EvaluationCaseResult, EvaluationReport
from database import Database
from services.evaluation_run_repository import EvaluationRunRepository


class EvaluationRunRepositoryTests(unittest.TestCase):
    def test_record_and_read_evaluation_report(self) -> None:
        db = Database(":memory:")
        repository = EvaluationRunRepository(db)
        report = EvaluationReport(
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            pass_rate=100.0,
            tool_selection_accuracy=100.0,
            average_duration_ms=1200.0,
            results=[
                EvaluationCaseResult(
                    id="inventory-p1002",
                    question="查询P1002库存",
                    passed=True,
                    expected_tools=["check_inventory"],
                    actual_tools=["check_inventory"],
                    answer="无库存",
                    duration_ms=1200,
                    failures=[],
                )
            ],
        )

        run_id = repository.record(report)
        stored = repository.get_run(run_id)
        summaries = repository.list_runs()

        self.assertIsNotNone(stored)
        self.assertEqual(stored.run_id, run_id)
        self.assertEqual(stored.pass_rate, 100.0)
        self.assertEqual(stored.results[0].actual_tools, ["check_inventory"])
        self.assertEqual(summaries[0].run_id, run_id)
        db.connection.close()


if __name__ == "__main__":
    unittest.main()
