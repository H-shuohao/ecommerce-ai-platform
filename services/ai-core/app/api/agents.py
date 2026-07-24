import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas.agents import AgentChatRequest, AgentChatResponse
from app.schemas.memory import ConversationSession
from app.schemas.observability import AgentRunDetail, AgentRunMetrics, AgentRunSummary
from services.agent_run_repository import agent_run_repository
from services.conversation_repository import conversation_repository
from services.presales_agent_service import presales_agent_service


router = APIRouter(prefix="/api/v1/agents", tags=["业务 Agent"])


def _duration_ms(started_at: float) -> int:
    return max(1, int((time.perf_counter() - started_at) * 1000))


def _record_failed_run(question: str, started_at: float, error: Exception) -> None:
    agent_run_repository.record(
        question=question,
        status="failed",
        duration_ms=_duration_ms(started_at),
        error=str(error),
    )


def _finalize_successful_run(
    request: AgentChatRequest,
    session_id: str,
    response: AgentChatResponse,
    started_at: float,
) -> AgentChatResponse:
    duration_ms = _duration_ms(started_at)
    run_id = agent_run_repository.record(
        question=request.question,
        status="success",
        duration_ms=duration_ms,
        answer=response.answer,
        rag_used=response.rag_used,
        tool_calls=[call.model_dump() for call in response.tool_calls],
    )
    conversation_repository.append_exchange(
        session_id,
        request.question,
        response.answer,
    )
    selected_product_ids = [
        str(call.arguments["product_id"]).strip().upper()
        for call in response.tool_calls
        if call.arguments.get("product_id")
    ]
    if selected_product_ids:
        conversation_repository.set_current_product_id(
            session_id,
            selected_product_ids[-1],
        )
    return response.model_copy(
        update={
            "run_id": run_id,
            "duration_ms": duration_ms,
            "session_id": session_id,
        }
    )


def _ndjson(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False, default=str) + "\n"


@router.post(
    "/presales/chat",
    response_model=AgentChatResponse,
    summary="运行售前咨询 Agent",
)
async def presales_chat(request: AgentChatRequest) -> AgentChatResponse:
    started_at = time.perf_counter()
    session_id = conversation_repository.ensure_session(request.session_id)
    history = conversation_repository.get_recent_messages(session_id, limit=6)
    current_product_id = conversation_repository.get_current_product_id(session_id)
    try:
        response = await presales_agent_service.run(
            request.question,
            history=history,
            current_product_id=current_product_id,
        )
    except (KeyError, TypeError, ValueError) as error:
        _record_failed_run(request.question, started_at, error)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        _record_failed_run(request.question, started_at, error)
        raise HTTPException(status_code=502, detail=str(error)) from error

    return _finalize_successful_run(
        request,
        session_id,
        response,
        started_at,
    )


@router.post(
    "/presales/chat/stream",
    response_class=StreamingResponse,
    summary="流式运行售前咨询 Agent",
    responses={
        200: {
            "content": {"application/x-ndjson": {}},
            "description": "按行返回 session、status、tool、delta、done 或 error 事件。",
        }
    },
)
async def presales_chat_stream(request: AgentChatRequest) -> StreamingResponse:
    started_at = time.perf_counter()
    session_id = conversation_repository.ensure_session(request.session_id)
    history = conversation_repository.get_recent_messages(session_id, limit=6)
    current_product_id = conversation_repository.get_current_product_id(session_id)

    async def generate_events() -> AsyncIterator[str]:
        yield _ndjson({"event": "session", "session_id": session_id})
        yield _ndjson(
            {
                "event": "status",
                "stage": "planning",
                "message": "正在分析问题并规划工具调用…",
            }
        )
        try:
            async for event in presales_agent_service.run_stream(
                request.question,
                history=history,
                current_product_id=current_product_id,
            ):
                if event["event"] != "complete":
                    yield _ndjson(event)
                    continue
                response = _finalize_successful_run(
                    request,
                    session_id,
                    event["response"],
                    started_at,
                )
                yield _ndjson(
                    {
                        "event": "done",
                        **response.model_dump(),
                    }
                )
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            _record_failed_run(request.question, started_at, error)
            yield _ndjson(
                {
                    "event": "error",
                    "code": "AGENT_EXECUTION_FAILED",
                    "message": str(error),
                    "session_id": session_id,
                }
            )

    return StreamingResponse(
        generate_events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/sessions/{session_id}",
    response_model=ConversationSession,
    summary="查看 Agent 会话历史",
)
async def get_conversation_session(session_id: str) -> ConversationSession:
    session = conversation_repository.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.get(
    "/runs",
    response_model=list[AgentRunSummary],
    summary="查询 Agent 运行记录",
)
async def list_agent_runs(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[AgentRunSummary]:
    return agent_run_repository.list_runs(limit=limit)


@router.get(
    "/runs/metrics",
    response_model=AgentRunMetrics,
    summary="查看 Agent 运行统计",
)
async def get_agent_run_metrics() -> AgentRunMetrics:
    return agent_run_repository.get_metrics()


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunDetail,
    summary="查询 Agent 运行详情",
)
async def get_agent_run(run_id: str) -> AgentRunDetail:
    run = agent_run_repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    return run
