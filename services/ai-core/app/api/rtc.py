import httpx
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.rtc import build_rtc_token, require_setting
from app.core.streaming import (
    chunk_delta_content,
    chunk_to_sse_json,
    chunk_usage,
    next_from_sync_iterator,
    should_stop_streaming,
    usage_value,
)
from config import settings
from services.llm_service import llm_service
from services.rag_service import rag_service
from services.utils import Signer


router = APIRouter(tags=["RTC"])


@router.post("/getScenes", summary="获取前端 RTC 场景")
async def get_scenes() -> dict[str, object]:
    room_id = settings.RTC_ROOM_ID
    user_id = settings.RTC_USER_ID
    token = build_rtc_token(room_id, user_id)

    return {
        "ResponseMetadata": {"Action": "getScenes"},
        "Result": {
            "scenes": [
                {
                    "scene": {
                        "id": "Custom",
                        "name": "自定义助手",
                        "botName": settings.AGENT_USER_ID,
                        "icon": "https://lf3-rtc-demo.volccdn.com/obj/rtc-aigc-assets/DoubaoAvatar.png",
                        "isInterruptMode": True,
                        "isVision": False,
                        "isScreenMode": False,
                        "isAvatarScene": None,
                        "avatarBgUrl": None,
                    },
                    "rtc": {
                        "AppId": settings.RTC_APP_ID,
                        "RoomId": room_id,
                        "UserId": user_id,
                        "Token": token,
                    },
                    "VoiceChat": {},
                }
            ]
        },
    }


@router.post("/proxy", summary="代理 RTC Start/StopVoiceChat 请求")
async def proxy(request: Request) -> dict[str, object]:
    action = request.query_params.get("Action")
    version = request.query_params.get("Version", "2024-12-01")

    try:
        incoming_body = await request.json()
    except Exception:
        incoming_body = {}

    target_app_id = require_setting(settings.RTC_APP_ID, "RTC_APP_ID")
    callback_base = require_setting(settings.SERVER_URL, "SERVER_URL").rstrip("/")

    if action == "StartVoiceChat":
        request_body = {
            "AppId": target_app_id,
            "RoomId": settings.RTC_ROOM_ID,
            "TaskId": settings.VOICE_CHAT_TASK_ID,
            "AgentConfig": {
                "TargetUserId": [settings.RTC_USER_ID],
                "WelcomeMessage": settings.AGENT_WELCOME_MESSAGE,
                "UserId": settings.AGENT_USER_ID,
                "EnableConversationStateCallback": True,
            },
            "Config": {
                "ASRConfig": {
                    "Provider": "volcano",
                    "ProviderParams": {
                        "Mode": "smallmodel",
                        "AppId": require_setting(settings.ASR_APP_ID, "ASR_APP_ID"),
                        "Cluster": "volcengine_streaming_common",
                    },
                },
                "TTSConfig": {
                    "Provider": "volcano",
                    "ProviderParams": {
                        "app": {
                            "appid": require_setting(settings.TTS_APP_ID, "TTS_APP_ID"),
                            "cluster": "volcano_tts",
                        },
                        "audio": {
                            "voice_type": "BV001_streaming",
                            "speed_ratio": 1,
                            "pitch_ratio": 1,
                            "volume_ratio": 1,
                        },
                    },
                },
                "LLMConfig": {
                    "Mode": "CustomLLM",
                    "Url": f"{callback_base}/api/chat_callback",
                    "Method": "POST",
                    "ApiType": "https" if callback_base.startswith("https") else "http",
                },
                "InterruptMode": 0,
            },
        }
    elif action == "StopVoiceChat":
        request_body = {
            "AppId": target_app_id,
            "RoomId": settings.RTC_ROOM_ID,
            "TaskId": settings.VOICE_CHAT_TASK_ID,
        }
    else:
        request_body = incoming_body

    host = "rtc.volcengineapi.com"
    request_data = {
        "method": "POST",
        "path": "/",
        "params": {"Action": action, "Version": version},
        "headers": {"Host": host, "Content-Type": "application/json"},
        "body": request_body,
    }
    signer = Signer(request_data, "rtc")
    signer.add_authorization(
        {
            "accessKeyId": require_setting(settings.VOLC_AK, "VOLC_ACCESS_KEY"),
            "secretKey": require_setting(settings.VOLC_SK, "VOLC_SECRET_KEY"),
        }
    )

    url = f"https://{host}?Action={action}&Version={version}"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=request_data["headers"],
            json=request_body,
            timeout=30.0,
        )
    return response.json()


@router.post(
    "/api/chat_callback",
    summary="接收 RTC 的 CustomLLM 流式回调",
)
async def chat_callback(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"text": ""}

    messages = data.get("messages", [])
    if not messages or messages[-1].get("role") != "user":
        return {"text": ""}

    async def generate_sse():
        question = messages[-1].get("content", "")
        request_start = time.time()

        rag_start = time.time()
        rag_result = await rag_service.retrieve_result(question)
        rag_context = rag_result.context if rag_result.relevant else ""
        print(
            f"[chat_callback] RAG 检索耗时: {time.time() - rag_start:.2f}s"
        )

        llm_start = time.time()
        total_usage = None
        generated_text = ""
        stream = llm_service.chat_stream(messages, rag_context)
        stream_end = object()

        while True:
            chunk = await next_from_sync_iterator(stream, stream_end)
            if chunk is stream_end:
                break

            usage = chunk_usage(chunk)
            if usage:
                total_usage = usage

            content = chunk_delta_content(chunk)
            if content:
                generated_text += content

            chunk_json = chunk_to_sse_json(chunk)
            if chunk_json:
                yield f"data: {chunk_json}\n\n"

            if should_stop_streaming(generated_text):
                break

        print(f"[chat_callback] LLM 调用耗时: {time.time() - llm_start:.2f}s")
        print(f"[chat_callback] 本轮总耗时: {time.time() - request_start:.2f}s")
        if total_usage:
            print(
                "[chat_callback] Token: "
                f"Total={usage_value(total_usage, 'total_tokens')}, "
                f"Prompt={usage_value(total_usage, 'prompt_tokens')}, "
                f"Completion={usage_value(total_usage, 'completion_tokens')}"
            )

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
