from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "请推荐一款适合油皮的商品",
                "session_id": None,
            }
        }
    )

    question: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, max_length=100)


class ToolCallTrace(BaseModel):
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]


class AgentChatResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    rag_used: bool
    run_id: str | None = None
    duration_ms: int | None = None
    session_id: str | None = None
