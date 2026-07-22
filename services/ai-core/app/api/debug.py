import json
import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.core.streaming import (
    chunk_delta_content,
    chunk_usage,
    next_from_sync_iterator,
    should_stop_streaming,
    usage_value,
)
from app.schemas.debug import DebugRequest, RagDebugResponse
from services.llm_service import llm_service
from services.rag_service import rag_service


router = APIRouter(prefix="/debug", tags=["AI 调试"])


def build_messages(request: DebugRequest) -> list[dict[str, str]]:
    messages = [
        {"role": message.role, "content": message.content}
        for message in request.history
    ]
    messages.append({"role": "user", "content": request.question})
    return messages


@router.get(
    "/rag",
    response_model=RagDebugResponse,
    summary="只测试知识库检索",
)
async def debug_rag(query: str) -> dict[str, object]:
    """Retrieve knowledge without calling the language model."""
    result = await rag_service.retrieve_result(query)
    context = result.context

    if result.relevant:
        status = "success"
    elif context:
        status = "irrelevant"
    else:
        status = "no_results_or_error"

    return {
        "query": query,
        "retrieved_context": context,
        "length": len(context),
        "score": result.score,
        "relevant": result.relevant,
        "reason": result.reason,
        "status": status,
    }


@router.post(
    "/chat",
    summary="流式测试 RAG + LLM",
    description="保留给流式响应测试；Swagger 手动调试优先使用 /debug/chat/json。",
)
async def debug_chat(request: DebugRequest) -> StreamingResponse:
    current_messages = build_messages(request)

    async def generate_text():
        full_response = ""
        rag_result = await rag_service.retrieve_result(request.question)
        rag_context = rag_result.context if rag_result.relevant else ""
        stream = llm_service.chat_stream(current_messages, rag_context)

        for chunk in stream:
            content = chunk_delta_content(chunk)
            if content:
                full_response += content
                yield content
                if should_stop_streaming(full_response):
                    break

        new_history = [
            {"role": message.role, "content": message.content}
            for message in request.history
        ]
        new_history.extend(
            [
                {"role": "user", "content": request.question},
                {"role": "assistant", "content": full_response},
            ]
        )
        print(json.dumps({"history": new_history}, ensure_ascii=False, indent=2))

    return StreamingResponse(generate_text(), media_type="text/plain")


@router.post(
    "/chat/json",
    response_class=PlainTextResponse,
    summary="在 Swagger 中测试 RAG + LLM",
)
async def debug_chat_json(request: DebugRequest) -> PlainTextResponse:
    request_start = time.time()
    current_messages = build_messages(request)

    rag_start = time.time()
    rag_result = await rag_service.retrieve_result(request.question)
    rag_context = rag_result.context if rag_result.relevant else ""
    rag_seconds = time.time() - rag_start

    llm_start = time.time()
    first_token_seconds = None
    generated_text = ""
    total_usage = None
    stream = llm_service.chat_stream(current_messages, rag_context)
    stream_end = object()

    try:
        while True:
            chunk = await next_from_sync_iterator(stream, stream_end)
            if chunk is stream_end:
                break

            usage = chunk_usage(chunk)
            if usage:
                total_usage = usage

            content = chunk_delta_content(chunk)
            if not content:
                continue
            if first_token_seconds is None:
                first_token_seconds = time.time() - llm_start
            generated_text += content
            if should_stop_streaming(generated_text):
                break
    finally:
        close_stream = getattr(stream, "close", None)
        if callable(close_stream):
            close_stream()

    llm_seconds = time.time() - llm_start
    total_seconds = time.time() - request_start
    first_token_display = (
        f"{first_token_seconds:.3f}s" if first_token_seconds is not None else "未返回"
    )
    print(
        "[Swagger] 耗时: "
        f"RAG={rag_seconds:.3f}s, 首Token={first_token_display}, "
        f"LLM={llm_seconds:.3f}s, 总计={total_seconds:.3f}s"
    )
    if total_usage:
        print(
            "[Swagger] Token: "
            f"Total={usage_value(total_usage, 'total_tokens')}, "
            f"Prompt={usage_value(total_usage, 'prompt_tokens')}, "
            f"Completion={usage_value(total_usage, 'completion_tokens')}"
        )

    return PlainTextResponse(generated_text, media_type="text/plain; charset=utf-8")
