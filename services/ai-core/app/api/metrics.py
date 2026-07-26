from dataclasses import asdict

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.http_metrics import http_metrics
from app.core.metric_alerts import evaluate_http_metrics
from config import settings


router = APIRouter(tags=["系统监控"])


@router.get(
    "/api/v1/metrics/http",
    summary="查看进程内HTTP请求指标",
)
async def get_http_metrics() -> dict:
    return asdict(http_metrics.snapshot())


@router.get(
    "/api/v1/metrics/alerts",
    summary="根据HTTP指标检查告警状态",
)
async def get_metric_alerts() -> dict:
    report = evaluate_http_metrics(
        http_metrics.snapshot(),
        minimum_samples=settings.METRIC_ALERT_MINIMUM_SAMPLES,
        p95_warning_ms=settings.METRIC_ALERT_P95_WARNING_MS,
        p95_critical_ms=settings.METRIC_ALERT_P95_CRITICAL_MS,
        error_rate_warning_percent=settings.METRIC_ALERT_ERROR_RATE_WARNING_PERCENT,
        error_rate_critical_percent=settings.METRIC_ALERT_ERROR_RATE_CRITICAL_PERCENT,
        in_flight_warning=settings.METRIC_ALERT_IN_FLIGHT_WARNING,
        in_flight_critical=settings.METRIC_ALERT_IN_FLIGHT_CRITICAL,
    )
    return asdict(report)


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
