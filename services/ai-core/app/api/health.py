from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import settings


router = APIRouter(tags=["系统"])


@router.get("/health", summary="检查后端是否正常运行")
async def health() -> dict[str, str]:
    """Return a lightweight liveness response for the HTTP service."""
    return {
        "status": "ok",
        "service": "xiaolan-ai-project-assistant",
        "docs": "/docs",
    }


def configured(*values: object) -> bool:
    """Check whether every required configuration value is present."""
    return all(bool(value) for value in values)


@router.get("/ready", summary="检查 AI 服务依赖配置是否就绪")
async def readiness() -> JSONResponse:
    components = {
        "llm": configured(settings.ARK_API_KEY, settings.ARK_ENDPOINT_ID),
        "rag": configured(
            settings.VOLC_AK,
            settings.VOLC_SK,
            settings.VOLC_ACCOUNT_ID,
            settings.KB_COLLECTION_NAME,
        ),
        "rtc": configured(
            settings.RTC_APP_ID,
            settings.RTC_ROOM_ID,
            settings.RTC_USER_ID,
        ),
    }

    core_ready = components["llm"] and components["rag"]
    return JSONResponse(
        status_code=200 if core_ready else 503,
        content={
            "status": "ready" if core_ready else "not_ready",
            "components": components,
        },
    )
