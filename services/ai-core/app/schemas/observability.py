from typing import Any, Literal

from pydantic import BaseModel


class StoredToolCall(BaseModel):
    sequence: int
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]


class AgentRunSummary(BaseModel):
    id: str
    agent_name: str
    question: str
    status: Literal["success", "failed"]
    rag_used: bool
    duration_ms: int
    created_at: str


class AgentRunDetail(AgentRunSummary):
    answer: str | None = None
    error: str | None = None
    tool_calls: list[StoredToolCall]


class ToolUsageMetric(BaseModel):
    tool: str
    call_count: int


class AgentRunMetrics(BaseModel):
    total_runs: int
    success_runs: int
    failed_runs: int
    success_rate: float
    average_duration_ms: float
    rag_used_runs: int
    rag_usage_rate: float
    total_tool_calls: int
    tool_usage: list[ToolUsageMetric]
