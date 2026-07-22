from typing import Any

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    name: str
    type: str
    required: bool
    description: str


class ToolDefinitionResponse(BaseModel):
    name: str
    description: str
    parameters: list[ToolParameter]


class ToolInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolInvokeResponse(BaseModel):
    tool: str
    success: bool
    data: Any = None
    error: str | None = None

