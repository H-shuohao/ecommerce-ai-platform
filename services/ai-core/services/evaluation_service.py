import json
import time
from pathlib import Path

from app.schemas.evaluations import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationReport,
)
from services.presales_agent_service import PresalesAgentService, presales_agent_service
from services.evaluation_run_repository import EvaluationRunRepository, evaluation_run_repository


CASES_PATH = Path(__file__).resolve().parents[1] / "data" / "presales_evaluation_cases.json"


class EvaluationService:
    def __init__(
        self,
        agent: PresalesAgentService = presales_agent_service,
        repository: EvaluationRunRepository = evaluation_run_repository,
    ) -> None:
        self.agent = agent
        self.repository = repository

    def list_cases(self) -> list[EvaluationCase]:
        with CASES_PATH.open("r", encoding="utf-8") as file:
            return [EvaluationCase(**item) for item in json.load(file)]

    @staticmethod
    def _evaluate_case(case: EvaluationCase, response) -> tuple[list[str], int]:
        failures: list[str] = []
        matched_tools = 0
        calls_by_name = {call.tool: call for call in response.tool_calls}

        for expected_tool in case.expected_tools:
            call = calls_by_name.get(expected_tool)
            if call is None:
                failures.append(f"缺少预期工具调用: {expected_tool}")
                continue
            expected_arguments = case.expected_arguments.get(expected_tool, {})
            wrong_arguments = {
                name: value
                for name, value in expected_arguments.items()
                if call.arguments.get(name) != value
            }
            if wrong_arguments:
                failures.append(f"工具 {expected_tool} 参数不符合预期")
                continue
            matched_tools += 1

        if not response.answer.strip():
            failures.append("最终回答为空")
        return failures, matched_tools

    async def run(self) -> EvaluationReport:
        cases = self.list_cases()
        results: list[EvaluationCaseResult] = []
        matched_tools = 0
        expected_tool_count = sum(len(case.expected_tools) for case in cases)

        for case in cases:
            started_at = time.perf_counter()
            try:
                response = await self.agent.run(case.question, history=[])
                failures, case_matched_tools = self._evaluate_case(case, response)
                matched_tools += case_matched_tools
                answer = response.answer
                actual_tools = [call.tool for call in response.tool_calls]
            except Exception as error:  # Keep evaluating the remaining cases.
                failures = [f"运行异常: {error}"]
                answer = None
                actual_tools = []
            duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
            results.append(
                EvaluationCaseResult(
                    id=case.id,
                    question=case.question,
                    passed=not failures,
                    expected_tools=case.expected_tools,
                    actual_tools=actual_tools,
                    answer=answer,
                    duration_ms=duration_ms,
                    failures=failures,
                )
            )

        passed_cases = sum(result.passed for result in results)
        total_cases = len(results)
        report = EvaluationReport(
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=total_cases - passed_cases,
            pass_rate=round(passed_cases / total_cases * 100, 2) if total_cases else 0.0,
            tool_selection_accuracy=(
                round(matched_tools / expected_tool_count * 100, 2)
                if expected_tool_count
                else 0.0
            ),
            average_duration_ms=(
                round(sum(result.duration_ms for result in results) / total_cases, 2)
                if total_cases
                else 0.0
            ),
            results=results,
        )
        run_id = self.repository.record(report)
        return report.model_copy(update={"run_id": run_id})


evaluation_service = EvaluationService()
