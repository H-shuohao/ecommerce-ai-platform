from typing import Any

from pydantic import BaseModel


class EvaluationCase(BaseModel):
    id: str
    question: str
    expected_tools: list[str]
    expected_arguments: dict[str, dict[str, Any]]


class EvaluationCaseResult(BaseModel):
    id: str
    question: str
    passed: bool
    expected_tools: list[str]
    actual_tools: list[str]
    answer: str | None = None
    duration_ms: int
    failures: list[str]


class EvaluationReport(BaseModel):
    run_id: str | None = None
    suite_name: str = "presales"
    suite_version: str = "v1"
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    tool_selection_accuracy: float
    average_duration_ms: float
    results: list[EvaluationCaseResult]


class EvaluationRunSummary(BaseModel):
    run_id: str
    suite_name: str
    suite_version: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    tool_selection_accuracy: float
    average_duration_ms: float
    created_at: str


class StoredEvaluationReport(EvaluationRunSummary):
    results: list[EvaluationCaseResult]


class EvaluationComparison(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    suite_name: str
    suite_version: str
    pass_rate_delta: float
    tool_selection_accuracy_delta: float
    average_duration_ms_delta: float
    improved_cases: list[str]
    regressed_cases: list[str]
    unchanged_cases: list[str]
    recommendation: str
