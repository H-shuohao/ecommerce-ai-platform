import time

from fastapi import APIRouter, HTTPException, Query

from app.schemas.agents import AgentChatRequest, AgentChatResponse
from app.schemas.memory import ConversationSession
from app.schemas.observability import AgentRunDetail, AgentRunMetrics, AgentRunSummary
from services.agent_run_repository import agent_run_repository
from services.conversation_repository import conversation_repository
from services.presales_agent_service import presales_agent_service


router = APIRouter(prefix="/api/v1/agents", tags=["业务 Agent"])


@router.post(
    "/presales/chat",
    response_model=AgentChatResponse,
    summary="运行售前咨询 Agent",
)
async def presales_chat(request: AgentChatRequest) -> AgentChatResponse:
    started_at = time.perf_counter()
    session_id = conversation_repository.ensure_session(request.session_id)
    history = conversation_repository.get_recent_messages(session_id, limit=6)
    try:
        response = await presales_agent_service.run(request.question, history=history)
    except (KeyError, TypeError, ValueError) as error:
        duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        agent_run_repository.record(
            question=request.question,
            status="failed",
            duration_ms=duration_ms,
            error=str(error),
        )
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
        agent_run_repository.record(
            question=request.question,
            status="failed",
            duration_ms=duration_ms,
            error=str(error),
        )
        raise HTTPException(status_code=502, detail=str(error)) from error

    duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
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
    return response.model_copy(
        update={
            "run_id": run_id,
            "duration_ms": duration_ms,
            "session_id": session_id,
        }
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
