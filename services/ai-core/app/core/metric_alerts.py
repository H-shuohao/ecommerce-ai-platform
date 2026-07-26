from dataclasses import dataclass
from typing import Literal

from app.core.http_metrics import HttpMetricsSnapshot


AlertSeverity = Literal["healthy", "warning", "critical"]


@dataclass(frozen=True)
class MetricAlert:
    code: str
    severity: Literal["warning", "critical"]
    message: str
    current_value: float
    threshold: float


@dataclass(frozen=True)
class MetricAlertReport:
    status: AlertSeverity
    evaluated: bool
    sample_size: int
    server_error_rate_percent: float
    alerts: list[MetricAlert]


def evaluate_http_metrics(
    snapshot: HttpMetricsSnapshot,
    *,
    minimum_samples: int,
    p95_warning_ms: float,
    p95_critical_ms: float,
    error_rate_warning_percent: float,
    error_rate_critical_percent: float,
    in_flight_warning: int,
    in_flight_critical: int,
) -> MetricAlertReport:
    total = snapshot.total_requests
    error_rate = (
        round(snapshot.server_error_requests / total * 100, 2) if total else 0.0
    )
    if snapshot.sample_size < minimum_samples:
        return MetricAlertReport(
            status="healthy",
            evaluated=False,
            sample_size=snapshot.sample_size,
            server_error_rate_percent=error_rate,
            alerts=[],
        )

    alerts: list[MetricAlert] = []
    _append_threshold_alert(
        alerts,
        code="HTTP_P95_LATENCY_HIGH",
        label="HTTP P95 延迟",
        current_value=snapshot.p95_duration_ms,
        warning_threshold=p95_warning_ms,
        critical_threshold=p95_critical_ms,
        unit="ms",
    )
    _append_threshold_alert(
        alerts,
        code="HTTP_SERVER_ERROR_RATE_HIGH",
        label="HTTP 5xx 错误率",
        current_value=error_rate,
        warning_threshold=error_rate_warning_percent,
        critical_threshold=error_rate_critical_percent,
        unit="%",
    )
    _append_threshold_alert(
        alerts,
        code="HTTP_IN_FLIGHT_HIGH",
        label="正在处理的请求数",
        current_value=float(snapshot.in_flight_requests),
        warning_threshold=float(in_flight_warning),
        critical_threshold=float(in_flight_critical),
        unit="",
    )
    status: AlertSeverity = "healthy"
    if any(alert.severity == "critical" for alert in alerts):
        status = "critical"
    elif alerts:
        status = "warning"
    return MetricAlertReport(
        status=status,
        evaluated=True,
        sample_size=snapshot.sample_size,
        server_error_rate_percent=error_rate,
        alerts=alerts,
    )


def _append_threshold_alert(
    alerts: list[MetricAlert],
    *,
    code: str,
    label: str,
    current_value: float,
    warning_threshold: float,
    critical_threshold: float,
    unit: str,
) -> None:
    severity: Literal["warning", "critical"] | None = None
    threshold = warning_threshold
    if current_value >= critical_threshold:
        severity = "critical"
        threshold = critical_threshold
    elif current_value >= warning_threshold:
        severity = "warning"
    if severity is None:
        return
    alerts.append(
        MetricAlert(
            code=code,
            severity=severity,
            message=(
                f"{label}当前为 {current_value:g}{unit}，"
                f"已达到{severity}阈值 {threshold:g}{unit}"
            ),
            current_value=current_value,
            threshold=threshold,
        )
    )
