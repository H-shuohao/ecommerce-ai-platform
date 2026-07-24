from typing import Any

from pydantic import BaseModel, Field


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
    failure_types: list[str] = Field(default_factory=list)


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
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    failure_summary: dict[str, int] = Field(default_factory=dict)
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
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    failure_summary: dict[str, int] = Field(default_factory=dict)
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
