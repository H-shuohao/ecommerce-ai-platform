import statistics
import threading
from collections import Counter, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class HttpMetricsSnapshot:
    total_requests: int
    in_flight_requests: int
    success_requests: int
    client_error_requests: int
    server_error_requests: int
    average_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float
    status_codes: dict[str, int]
    methods: dict[str, int]
    sample_size: int


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(len(ordered) * percentile + 0.999999)))
    return round(ordered[rank - 1], 2)


class HttpMetricsRegistry:
    """Process-local request metrics with a bounded latency sample."""

    def __init__(self, sample_limit: int = 2000) -> None:
        self._sample_limit = sample_limit
        self._lock = threading.Lock()
        self._total = 0
        self._in_flight = 0
        self._status_codes: Counter[str] = Counter()
        self._methods: Counter[str] = Counter()
        self._durations: deque[float] = deque(maxlen=sample_limit)

    def start_request(self) -> None:
        with self._lock:
            self._in_flight += 1

    def finish_request(
        self,
        *,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._total += 1
            self._status_codes[str(status_code)] += 1
            self._methods[method.upper()] += 1
            self._durations.append(duration_ms)

    def snapshot(self) -> HttpMetricsSnapshot:
        with self._lock:
            durations = list(self._durations)
            status_codes = dict(sorted(self._status_codes.items()))
            methods = dict(sorted(self._methods.items()))
            total = self._total
            in_flight = self._in_flight
        success = sum(
            count
            for code, count in status_codes.items()
            if 200 <= int(code) < 400
        )
        client_errors = sum(
            count
            for code, count in status_codes.items()
            if 400 <= int(code) < 500
        )
        server_errors = sum(
            count
            for code, count in status_codes.items()
            if int(code) >= 500
        )
        return HttpMetricsSnapshot(
            total_requests=total,
            in_flight_requests=in_flight,
            success_requests=success,
            client_error_requests=client_errors,
            server_error_requests=server_errors,
            average_duration_ms=(
                round(statistics.fmean(durations), 2) if durations else 0.0
            ),
            p50_duration_ms=nearest_rank(durations, 0.50),
            p95_duration_ms=nearest_rank(durations, 0.95),
            p99_duration_ms=nearest_rank(durations, 0.99),
            status_codes=status_codes,
            methods=methods,
            sample_size=len(durations),
        )

    def clear(self) -> None:
        with self._lock:
            self._total = 0
            self._in_flight = 0
            self._status_codes.clear()
            self._methods.clear()
            self._durations.clear()

    def prometheus_text(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP ai_core_http_requests_total Total HTTP requests.",
            "# TYPE ai_core_http_requests_total counter",
        ]
        for status_code, count in snapshot.status_codes.items():
            lines.append(
                'ai_core_http_requests_total'
                f'{{status_code="{status_code}"}} {count}'
            )
        lines.extend(
            [
                "# HELP ai_core_http_requests_in_flight Current in-flight requests.",
                "# TYPE ai_core_http_requests_in_flight gauge",
                f"ai_core_http_requests_in_flight {snapshot.in_flight_requests}",
                "# HELP ai_core_http_request_duration_ms Recent request latency.",
                "# TYPE ai_core_http_request_duration_ms gauge",
                (
                    'ai_core_http_request_duration_ms{quantile="0.50"} '
                    f"{snapshot.p50_duration_ms}"
                ),
                (
                    'ai_core_http_request_duration_ms{quantile="0.95"} '
                    f"{snapshot.p95_duration_ms}"
                ),
                (
                    'ai_core_http_request_duration_ms{quantile="0.99"} '
                    f"{snapshot.p99_duration_ms}"
                ),
                (
                    'ai_core_http_request_duration_ms{quantile="average"} '
                    f"{snapshot.average_duration_ms}"
                ),
            ]
        )
        return "\n".join(lines) + "\n"


http_metrics = HttpMetricsRegistry()
