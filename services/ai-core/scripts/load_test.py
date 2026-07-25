import argparse
import asyncio
import json
import os
import platform
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


@dataclass(frozen=True)
class Sample:
    status_code: int | None
    duration_ms: float
    error: str | None = None


@dataclass(frozen=True)
class LoadTestReport:
    profile: str
    target_url: str
    total_requests: int
    concurrency: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    throughput_rps: float
    average_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    wall_time_seconds: float
    status_codes: dict[str, int]
    errors: dict[str, int]
    generated_at: str
    environment: str


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(len(ordered) * percentile + 0.999999)))
    return round(ordered[rank - 1], 2)


def build_report(
    *,
    profile: str,
    target_url: str,
    total_requests: int,
    concurrency: int,
    samples: list[Sample],
    wall_time_seconds: float,
) -> LoadTestReport:
    durations = [sample.duration_ms for sample in samples]
    successful = sum(
        1
        for sample in samples
        if (
            sample.status_code is not None
            and 200 <= sample.status_code < 400
            and sample.error is None
        )
    )
    failed = total_requests - successful
    status_codes = Counter(
        str(sample.status_code)
        for sample in samples
        if sample.status_code is not None
    )
    errors = Counter(sample.error for sample in samples if sample.error)
    return LoadTestReport(
        profile=profile,
        target_url=target_url,
        total_requests=total_requests,
        concurrency=concurrency,
        successful_requests=successful,
        failed_requests=failed,
        success_rate=round(successful / total_requests * 100, 2),
        throughput_rps=round(total_requests / wall_time_seconds, 2),
        average_duration_ms=round(statistics.fmean(durations), 2),
        p50_duration_ms=nearest_rank(durations, 0.50),
        p95_duration_ms=nearest_rank(durations, 0.95),
        p99_duration_ms=nearest_rank(durations, 0.99),
        min_duration_ms=round(min(durations), 2),
        max_duration_ms=round(max(durations), 2),
        wall_time_seconds=round(wall_time_seconds, 2),
        status_codes=dict(sorted(status_codes.items())),
        errors=dict(errors),
        generated_at=datetime.now(timezone.utc).isoformat(),
        environment=f"{platform.system()} {platform.release()} / Python {platform.python_version()}",
    )


AGENT_SCENARIOS: tuple[tuple[str, str], ...] = (
    ("\u8bf7\u67e5\u8be2\u5546\u54c1 P1002 \u5f53\u524d\u662f\u5426\u6709\u5e93\u5b58", "check_inventory"),
    ("\u5e2e\u6211\u67e5\u8be2\u8ba2\u5355 O20260720001 \u7684\u72b6\u6001", "query_order"),
    ("\u8bf7\u63a8\u8350\u4e00\u6b3e\u9002\u5408\u6cb9\u76ae\u7684\u5546\u54c1", "search_products"),
    ("\u8bf7\u4ecb\u7ecd\u5546\u54c1 P1001 \u7684\u8be6\u7ec6\u4fe1\u606f", "get_product"),
)


def _request_spec(profile: str, index: int) -> tuple[str, str, dict[str, Any] | None]:
    if profile == "commerce":
        return "GET", "/api/v1/products?keyword=油皮", None
    if profile == "agent":
        question, _ = AGENT_SCENARIOS[index % len(AGENT_SCENARIOS)]
        return (
            "POST",
            "/api/v1/agents/presales/chat",
            {
                "question": question,
                "session_id": f"load-test-{index}-{uuid4().hex[:8]}",
            },
        )
    raise ValueError(f"未知压测档位: {profile}")


def _validate_agent_response(response: httpx.Response, index: int) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return "InvalidJsonResponse"
    if not isinstance(payload, dict) or not str(payload.get("answer", "")).strip():
        return "MissingAgentAnswer"
    tool_calls = payload.get("tool_calls")
    if not isinstance(tool_calls, list):
        return "MissingToolCalls"
    actual_tools = {
        str(call.get("tool"))
        for call in tool_calls
        if isinstance(call, dict) and call.get("tool")
    }
    _, expected_tool = AGENT_SCENARIOS[index % len(AGENT_SCENARIOS)]
    if expected_tool not in actual_tools:
        return f"ExpectedToolNotCalled:{expected_tool}"
    return None


async def _run_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    *,
    profile: str,
    index: int,
) -> Sample:
    method, path, body = _request_spec(profile, index)
    async with semaphore:
        started_at = time.perf_counter()
        try:
            response = await client.request(method, path, json=body)
            duration_ms = (time.perf_counter() - started_at) * 1000
            validation_error = None
            if 200 <= response.status_code < 400 and profile == "agent":
                validation_error = _validate_agent_response(response, index)
            return Sample(
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                error=validation_error,
            )
        except Exception as error:
            duration_ms = (time.perf_counter() - started_at) * 1000
            return Sample(
                status_code=None,
                duration_ms=round(duration_ms, 2),
                error=type(error).__name__,
            )


async def run_load_test(
    *,
    base_url: str,
    profile: str,
    total_requests: int,
    concurrency: int,
    timeout_seconds: float,
    api_key: str | None,
) -> LoadTestReport:
    headers = {"X-API-Key": api_key} if api_key else {}
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout_seconds,
        limits=limits,
    ) as client:
        # Warm up imports, connection pooling and cache; do not include it in metrics.
        await _run_one(client, semaphore, profile=profile, index=-1)
        started_at = time.perf_counter()
        samples = await asyncio.gather(
            *(
                _run_one(
                    client,
                    semaphore,
                    profile=profile,
                    index=index,
                )
                for index in range(total_requests)
            )
        )
        wall_time = time.perf_counter() - started_at

    return build_report(
        profile=profile,
        target_url=base_url,
        total_requests=total_requests,
        concurrency=concurrency,
        samples=samples,
        wall_time_seconds=wall_time,
    )


def to_markdown(report: LoadTestReport) -> str:
    return f"""# AI Core 本地压测报告

> 本报告由 `scripts/load_test.py` 自动生成。结果仅代表本机回环环境和本次配置，
> 不等同于公网或生产环境容量。

| 指标 | 结果 |
|---|---:|
| 压测档位 | {report.profile} |
| 请求总数 | {report.total_requests} |
| 并发数 | {report.concurrency} |
| 成功率 | {report.success_rate}% |
| 吞吐量 | {report.throughput_rps} req/s |
| 平均耗时 | {report.average_duration_ms} ms |
| P50 | {report.p50_duration_ms} ms |
| P95 | {report.p95_duration_ms} ms |
| P99 | {report.p99_duration_ms} ms |
| 最小/最大耗时 | {report.min_duration_ms} / {report.max_duration_ms} ms |
| 总墙钟时间 | {report.wall_time_seconds} s |

- 目标地址：`{report.target_url}`
- 状态码：`{json.dumps(report.status_codes, ensure_ascii=False)}`
- 错误分类：`{json.dumps(report.errors, ensure_ascii=False)}`
- 运行环境：{report.environment}
- 生成时间：{report.generated_at}

## 边界说明

- `commerce` 档位测试商品查询、HTTP中间件、缓存和JSON序列化，不调用大模型。
- `agent` 档位会真实调用Agent与大模型，运行前应确认额度和限流配置。
- 当前服务为单机SQLite作品集架构，该数字不能宣传为企业生产环境承载能力。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Core 可重复并发压测工具")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--profile", choices=("commerce", "agent"), default="commerce")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--output", help="可选Markdown报告输出路径")
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error("requests 和 concurrency 必须大于0")

    report = asyncio.run(
        run_load_test(
            base_url=args.base_url.rstrip("/"),
            profile=args.profile,
            total_requests=args.requests,
            concurrency=min(args.concurrency, args.requests),
            timeout_seconds=args.timeout,
            api_key=os.getenv("LOAD_TEST_API_KEY"),
        )
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(to_markdown(report), encoding="utf-8")
        print(f"Markdown报告已写入: {output_path.resolve()}")
    return 0 if report.failed_requests == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
