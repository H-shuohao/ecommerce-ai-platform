import json
import math
import time
from collections import Counter
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
    def _evaluate_case(
        case: EvaluationCase,
        response,
    ) -> tuple[list[str], list[str], int]:
        failures: list[str] = []
        failure_types: list[str] = []
        matched_tools = 0
        calls_by_name = {call.tool: call for call in response.tool_calls}

        for expected_tool in case.expected_tools:
            call = calls_by_name.get(expected_tool)
            if call is None:
                failures.append(f"缺少预期工具调用: {expected_tool}")
                failure_types.append("missing_tool")
                continue
            expected_arguments = case.expected_arguments.get(expected_tool, {})
            wrong_arguments = {
                name: value
                for name, value in expected_arguments.items()
                if call.arguments.get(name) != value
            }
            if wrong_arguments:
                failures.append(f"工具 {expected_tool} 参数不符合预期")
                failure_types.append("wrong_arguments")
                continue
            matched_tools += 1

        if not response.answer.strip():
            failures.append("最终回答为空")
            failure_types.append("empty_answer")
        return failures, failure_types, matched_tools

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        rank = max(1, math.ceil(percentile * len(ordered)))
        return float(ordered[rank - 1])

    async def run(self) -> EvaluationReport:
        cases = self.list_cases()
        results: list[EvaluationCaseResult] = []
        matched_tools = 0
        expected_tool_count = sum(len(case.expected_tools) for case in cases)

        for case in cases:
            started_at = time.perf_counter()
            try:
                response = await self.agent.run(case.question, history=[])
                failures, failure_types, case_matched_tools = self._evaluate_case(
                    case,
                    response,
                )
                matched_tools += case_matched_tools
                answer = response.answer
                actual_tools = [call.tool for call in response.tool_calls]
            except Exception as error:  # Keep evaluating the remaining cases.
                failures = [f"运行异常: {error}"]
                failure_types = ["runtime_error"]
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
                    failure_types=sorted(set(failure_types)),
                )
            )

        passed_cases = sum(result.passed for result in results)
        total_cases = len(results)
        durations = [result.duration_ms for result in results]
        failure_summary = Counter(
            failure_type
            for result in results
            for failure_type in result.failure_types
        )
        report = EvaluationReport(
            suite_version="v2",
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
                round(sum(durations) / total_cases, 2)
                if total_cases
                else 0.0
            ),
            p50_duration_ms=self._percentile(durations, 0.50),
            p95_duration_ms=self._percentile(durations, 0.95),
            failure_summary=dict(sorted(failure_summary.items())),
            results=results,
        )
        run_id = self.repository.record(report)
        return report.model_copy(update={"run_id": run_id})


evaluation_service = EvaluationService()
