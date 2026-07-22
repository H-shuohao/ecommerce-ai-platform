import unittest

from app.schemas.agents import AgentChatResponse, ToolCallTrace
from database import Database
from services.evaluation_service import EvaluationService
from services.evaluation_run_repository import EvaluationRunRepository


class FakeEvaluationAgent:
    async def run(self, question: str, history=None) -> AgentChatResponse:
        if "P1002" in question:
            tool = "check_inventory"
            arguments = {"product_id": "P1002"}
        elif "O20260720001" in question:
            tool = "query_order"
            arguments = {"order_id": "O20260720001"}
        elif "油皮" in question:
            tool = "search_products"
            arguments = {"keyword": "油皮"}
        else:
            tool = "get_product"
            arguments = {"product_id": "P1001"}
        return AgentChatResponse(
            answer="评测回答",
            tool_calls=[ToolCallTrace(tool=tool, arguments=arguments, result={})],
            rag_used=False,
        )


class EvaluationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_cases_pass_with_expected_tools(self) -> None:
        db = Database(":memory:")
        service = EvaluationService(
            agent=FakeEvaluationAgent(),
            repository=EvaluationRunRepository(db),
        )

        report = await service.run()

        self.assertEqual(report.total_cases, 4)
        self.assertEqual(report.passed_cases, 4)
        self.assertEqual(report.pass_rate, 100.0)
        self.assertEqual(report.tool_selection_accuracy, 100.0)
        self.assertIsNotNone(report.run_id)
        self.assertTrue(all(result.passed for result in report.results))
        db.connection.close()


if __name__ == "__main__":
    unittest.main()
