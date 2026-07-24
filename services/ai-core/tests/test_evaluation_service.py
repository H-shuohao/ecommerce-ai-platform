import unittest

from app.schemas.agents import AgentChatResponse, ToolCallTrace
from app.schemas.evaluations import EvaluationCase
from database import Database
from services.evaluation_service import EvaluationService
from services.evaluation_run_repository import EvaluationRunRepository


class FakeEvaluationAgent:
    async def run(self, question: str, history=None) -> AgentChatResponse:
        if any(word in question for word in ("库存", "现货", "有货")):
            tool = "check_inventory"
            product_id = next(
                value
                for value in ("P1001", "P1002", "P2001", "P3001")
                if value in question
            )
            arguments = {"product_id": product_id}
        elif "订单" in question or "物流" in question:
            tool = "query_order"
            order_id = next(
                value
                for value in ("O20260720001", "O20260720002")
                if value in question
            )
            arguments = {"order_id": order_id}
        elif "素材" in question:
            tool = "search_media_assets"
            product_id = "P1001" if "P1001" in question else "P2001"
            asset_type = "video" if "视频" in question else "image"
            arguments = {
                "product_id": product_id,
                "asset_type": asset_type,
            }
        elif any(
            word in question
            for word in ("油皮", "敏感肌", "通勤", "数码类")
        ):
            tool = "search_products"
            arguments = {}
        else:
            tool = "get_product"
            product_id = next(
                value
                for value in ("P1001", "P2002", "P3001")
                if value in question
            )
            arguments = {"product_id": product_id}
        return AgentChatResponse(
            answer="评测回答",
            tool_calls=[ToolCallTrace(tool=tool, arguments=arguments, result={})],
            rag_used=False,
        )


class EvaluationServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_failure_types_are_machine_countable(self) -> None:
        case = EvaluationCase(
            id="inventory",
            question="查询库存",
            expected_tools=["check_inventory"],
            expected_arguments={"check_inventory": {"product_id": "P1002"}},
        )
        response = AgentChatResponse(
            answer="",
            tool_calls=[
                ToolCallTrace(
                    tool="check_inventory",
                    arguments={"product_id": "P1001"},
                    result={},
                )
            ],
            rag_used=False,
        )

        failures, failure_types, matched = EvaluationService._evaluate_case(
            case,
            response,
        )

        self.assertEqual(matched, 0)
        self.assertEqual(
            failure_types,
            ["wrong_arguments", "empty_answer"],
        )
        self.assertEqual(len(failures), 2)

    def test_percentiles_use_nearest_rank(self) -> None:
        durations = [100, 200, 300, 400, 1000]

        self.assertEqual(EvaluationService._percentile(durations, 0.50), 300.0)
        self.assertEqual(EvaluationService._percentile(durations, 0.95), 1000.0)

    async def test_all_cases_pass_with_expected_tools(self) -> None:
        db = Database(":memory:")
        service = EvaluationService(
            agent=FakeEvaluationAgent(),
            repository=EvaluationRunRepository(db),
        )

        report = await service.run()

        self.assertEqual(report.total_cases, 16)
        self.assertEqual(report.passed_cases, 16)
        self.assertEqual(report.pass_rate, 100.0)
        self.assertEqual(report.tool_selection_accuracy, 100.0)
        self.assertGreaterEqual(report.p95_duration_ms, report.p50_duration_ms)
        self.assertEqual(report.failure_summary, {})
        self.assertEqual(report.suite_version, "v2")
        self.assertIsNotNone(report.run_id)
        self.assertTrue(all(result.passed for result in report.results))
        db.connection.close()


if __name__ == "__main__":
    unittest.main()
