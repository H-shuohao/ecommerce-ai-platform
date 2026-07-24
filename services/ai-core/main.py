import uvicorn
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.api.agents import router as agents_router
from app.api.commerce import router as commerce_router
from app.api.content_agents import router as content_agents_router
from app.api.debug import router as debug_router
from app.api.data_platform import router as data_platform_router
from app.api.evaluations import router as evaluations_router
from app.api.health import router as health_router
from app.api.live_clips import router as live_clips_router
from app.api.media_assets import router as media_assets_router
from app.api.rtc import router as rtc_router
from app.api.tools import router as tools_router
from app.api.web import router as web_router
from config import settings
from pathlib import Path
from app.mcp.server import commerce_mcp
from app.core.security import (
    Role,
    admin_access,
    resolve_principal,
    service_access,
    viewer_access,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with commerce_mcp.session_manager.run():
        yield

OPENAPI_TAGS = [
    {"name": "系统", "description": "服务状态与调试入口。"},
    {"name": "AI 调试", "description": "单独测试 RAG 检索和大模型回答。"},
    {"name": "RTC", "description": "前端场景、语音任务代理和 RTC 回调。"},
    {"name": "电商数据", "description": "模拟商品、库存和订单查询。"},
    {"name": "Agent 工具", "description": "Agent 可发现和调用的业务工具。"},
    {"name": "业务 Agent", "description": "面向电商业务的 Agent 执行入口。"},
]

app = FastAPI(
    title="小懒 AI 项目助手调试 API",
    description=(
        "用于分别验证知识库检索、LLM 回答和 RTC 语音链路。"
        "建议先测试 /debug/rag，再测试 /debug/chat/json，最后测试 RTC。"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)


@app.middleware("http")
async def protect_mcp_endpoint(request: Request, call_next):
    if request.url.path.startswith("/mcp") and settings.API_AUTH_ENABLED:
        try:
            principal = resolve_principal(request.headers.get("X-API-Key"))
        except HTTPException as error:
            return JSONResponse(
                status_code=error.status_code,
                content={"detail": error.detail},
                headers=error.headers,
            )
        if principal.role not in {Role.SERVICE, Role.ADMIN}:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "当前身份没有访问 MCP 的权限"},
            )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(debug_router, dependencies=[Depends(service_access)])
app.include_router(rtc_router, dependencies=[Depends(service_access)])
app.include_router(commerce_router, dependencies=[Depends(viewer_access)])
app.include_router(tools_router, dependencies=[Depends(viewer_access)])
app.include_router(agents_router, dependencies=[Depends(service_access)])
app.include_router(content_agents_router, dependencies=[Depends(service_access)])
app.include_router(evaluations_router, dependencies=[Depends(admin_access)])
app.include_router(data_platform_router, dependencies=[Depends(admin_access)])
app.include_router(media_assets_router, dependencies=[Depends(service_access)])
app.include_router(live_clips_router, dependencies=[Depends(service_access)])
app.include_router(web_router)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "web" / "static"),
    name="static",
)
app.mount("/mcp", commerce_mcp.streamable_http_app(), name="commerce-mcp")


if __name__ == "__main__":
    print("Server running at http://127.0.0.1:8000")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
    )
