from dataclasses import asdict

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.http_metrics import http_metrics


router = APIRouter(tags=["系统监控"])


@router.get(
    "/api/v1/metrics/http",
    summary="查看进程内HTTP请求指标",
)
async def get_http_metrics() -> dict:
    return asdict(http_metrics.snapshot())


@router.get(
    "/metrics",
    summary="导出Prometheus文本指标",
    response_class=PlainTextResponse,
    include_in_schema=False,
)
async def export_prometheus_metrics() -> PlainTextResponse:
    return PlainTextResponse(
        http_metrics.prometheus_text(),
        media_type="text/plain; version=0.0.4",
    )
