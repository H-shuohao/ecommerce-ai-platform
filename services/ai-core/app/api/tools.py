from fastapi import APIRouter, HTTPException

from app.schemas.tools import (
    ToolDefinitionResponse,
    ToolInvokeRequest,
    ToolInvokeResponse,
)
from app.tools.registry import tool_registry


router = APIRouter(prefix="/api/v1/tools", tags=["Agent 工具"])


@router.get("", response_model=list[ToolDefinitionResponse], summary="列出 Agent 工具")
async def list_tools() -> list[ToolDefinitionResponse]:
    return tool_registry.list_tools()


@router.post(
    "/{tool_name}/invoke",
    response_model=ToolInvokeResponse,
    summary="调用指定 Agent 工具",
)
async def invoke_tool(
    tool_name: str,
    request: ToolInvokeRequest,
) -> ToolInvokeResponse:
    try:
        data = tool_registry.invoke(tool_name, request.arguments)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return ToolInvokeResponse(tool=tool_name, success=True, data=data)

