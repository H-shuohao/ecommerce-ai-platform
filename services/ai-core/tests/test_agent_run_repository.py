import unittest

from database import Database
from services.agent_run_repository import AgentRunRepository


class AgentRunRepositoryTests(unittest.TestCase):
    def test_record_and_read_agent_run(self) -> None:
        db = Database(":memory:")
        repository = AgentRunRepository(db)
        run_id = repository.record(
            question="查询库存",
            status="success",
            duration_ms=123,
            answer="库存为 36",
            rag_used=False,
            tool_calls=[
                {
                    "tool": "check_inventory",
                    "arguments": {"product_id": "P1001"},
                    "result": {"quantity": 36},
                }
            ],
        )

        detail = repository.get_run(run_id)
        summaries = repository.list_runs()

        self.assertIsNotNone(detail)
        self.assertEqual(detail.answer, "库存为 36")
        self.assertEqual(detail.tool_calls[0].tool, "check_inventory")
        self.assertEqual(summaries[0].id, run_id)
        db.connection.close()

    def test_calculate_agent_run_metrics(self) -> None:
        db = Database(":memory:")
        repository = AgentRunRepository(db)
        repository.record(
            question="查询库存",
            status="success",
            duration_ms=100,
            rag_used=True,
            tool_calls=[
                {
                    "tool": "check_inventory",
                    "arguments": {"product_id": "P1001"},
                    "result": {"quantity": 36},
                }
            ],
        )
        repository.record(
            question="失败请求",
            status="failed",
            duration_ms=300,
            error="模型服务异常",
        )

        metrics = repository.get_metrics()

        self.assertEqual(metrics.total_runs, 2)
        self.assertEqual(metrics.success_runs, 1)
        self.assertEqual(metrics.failed_runs, 1)
        self.assertEqual(metrics.success_rate, 50.0)
        self.assertEqual(metrics.average_duration_ms, 200.0)
        self.assertEqual(metrics.rag_usage_rate, 50.0)
        self.assertEqual(metrics.total_tool_calls, 1)
        self.assertEqual(metrics.tool_usage[0].tool, "check_inventory")
        db.connection.close()


if __name__ == "__main__":
    unittest.main()
