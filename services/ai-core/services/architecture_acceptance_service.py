import asyncio
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

import httpx


CaseStatus = Literal["passed", "warning", "failed", "skipped"]
AcceptanceMode = Literal["quick", "full"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]


PROJECT_NAMES = {
    1: "Agent Runtime 与共享运行底座",
    2: "售前咨询 Agent",
    3: "轻量 AI 数据中台",
    4: "直播切片 Agent",
    5: "内容运营 Agent",
    6: "MCP 共享层",
    7: "多模态素材中心",
    8: "Agent 评测与运行可观测",
}


@dataclass
class AcceptanceCaseResult:
    project_id: int
    case_id: str
    name: str
    status: CaseStatus
    duration_ms: int
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class AcceptanceProjectResult:
    project_id: int
    name: str
    status: CaseStatus
    passed_cases: int
    warning_cases: int
    failed_cases: int
    skipped_cases: int
    cases: list[AcceptanceCaseResult]


@dataclass
class ArchitectureAcceptanceReport:
    run_id: str
    mode: AcceptanceMode
    started_at: str
    finished_at: str
    duration_ms: int
    status: Literal["passed", "passed_with_warnings", "failed"]
    total_cases: int
    passed_cases: int
    warning_cases: int
    failed_cases: int
    skipped_cases: int
    pass_rate: float
    projects: list[AcceptanceProjectResult]
    environment: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


CaseAction = Callable[[], Awaitable[tuple[CaseStatus, str, dict[str, Any]]]]


class ArchitectureAcceptanceRunner:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8000",
        api_key: str | None = None,
        timeout_seconds: float = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        headers = {"X-API-Key": api_key} if api_key else {}
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout_seconds,
        )
        self.results: list[AcceptanceCaseResult] = []
        self.run_id = str(uuid.uuid4())

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def run(
        self,
        *,
        mode: AcceptanceMode = "quick",
        run_evaluation: bool = False,
    ) -> ArchitectureAcceptanceReport:
        started = time.perf_counter()
        started_at = datetime.now().astimezone().isoformat()
        try:
            await self._run_project_1()
            await self._run_project_2(mode)
            await self._run_project_3()
            await self._run_project_4(mode)
            await self._run_project_5(mode)
            await self._run_project_6()
            await self._run_project_7()
            await self._run_project_8(run_evaluation)
        finally:
            await self.close()
        finished_at = datetime.now().astimezone().isoformat()
        projects = self._build_projects()
        passed = sum(item.status == "passed" for item in self.results)
        warnings = sum(item.status == "warning" for item in self.results)
        failed = sum(item.status == "failed" for item in self.results)
        skipped = sum(item.status == "skipped" for item in self.results)
        evaluated = passed + warnings + failed
        status = (
            "failed"
            if failed
            else "passed_with_warnings"
            if warnings or skipped
            else "passed"
        )
        return ArchitectureAcceptanceReport(
            run_id=self.run_id,
            mode=mode,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(1, int((time.perf_counter() - started) * 1000)),
            status=status,
            total_cases=len(self.results),
            passed_cases=passed,
            warning_cases=warnings,
            failed_cases=failed,
            skipped_cases=skipped,
            pass_rate=round(passed / evaluated * 100, 2) if evaluated else 0.0,
            projects=projects,
            environment={
                "base_url": self.base_url,
                "python": sys.version.split()[0],
                "active_evaluation": run_evaluation,
            },
        )

    async def _case(
        self,
        project_id: int,
        case_id: str,
        name: str,
        action: CaseAction,
    ) -> None:
        started = time.perf_counter()
        try:
            status, summary, evidence = await action()
            result = AcceptanceCaseResult(
                project_id=project_id,
                case_id=case_id,
                name=name,
                status=status,
                duration_ms=max(1, int((time.perf_counter() - started) * 1000)),
                summary=summary,
                evidence=evidence,
            )
        except Exception as error:
            result = AcceptanceCaseResult(
                project_id=project_id,
                case_id=case_id,
                name=name,
                status="failed",
                duration_ms=max(1, int((time.perf_counter() - started) * 1000)),
                summary="验收执行失败",
                error=str(error),
            )
        self.results.append(result)
        marker = {
            "passed": "PASS",
            "warning": "WARN",
            "failed": "FAIL",
            "skipped": "SKIP",
        }[result.status]
        print(
            f"[{marker}] 项目{project_id} {name} "
            f"({result.duration_ms} ms) - {result.summary}",
            flush=True,
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        expected_status: int = 200,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any] | list[Any], httpx.Response]:
        response = await self.client.request(
            method,
            path,
            json=json_body,
            headers=headers,
        )
        if response.status_code != expected_status:
            body = response.text[:500].replace("\n", " ")
            raise AssertionError(
                f"{method} {path} 返回 {response.status_code}，预期 "
                f"{expected_status}；响应: {body}"
            )
        try:
            return response.json(), response
        except ValueError as error:
            raise AssertionError(f"{method} {path} 没有返回合法 JSON") from error

    async def _run_project_1(self) -> None:
        async def health():
            body, response = await self._request_json("GET", "/health")
            if body.get("status") != "ok":
                raise AssertionError(f"健康状态异常: {body}")
            request_id = response.headers.get("x-request-id")
            if not request_id:
                raise AssertionError("响应头缺少 X-Request-ID")
            return (
                "passed",
                "HTTP 服务存活且请求链路可追踪",
                {"service": body.get("service"), "request_id_present": True},
            )

        async def readiness():
            body, _ = await self._request_json("GET", "/ready")
            components = body.get("components", {})
            if body.get("status") != "ready":
                raise AssertionError(f"核心依赖未就绪: {components}")
            missing_optional = [
                name for name, ready in components.items() if not ready
            ]
            status: CaseStatus = "warning" if missing_optional else "passed"
            summary = (
                f"核心依赖就绪；可选能力未配置: {', '.join(missing_optional)}"
                if missing_optional
                else "全部依赖均已就绪"
            )
            return status, summary, {"components": components}

        async def run_metrics():
            body, _ = await self._request_json(
                "GET",
                "/api/v1/agents/runs/metrics",
            )
            required = {"total_runs", "success_rate", "average_duration_ms"}
            if not required.issubset(body):
                raise AssertionError("运行指标字段不完整")
            return (
                "passed",
                "Agent 运行数据能够持久化并汇总",
                {
                    "total_runs": body["total_runs"],
                    "success_rate": body["success_rate"],
                    "average_duration_ms": body["average_duration_ms"],
                },
            )

        await self._case(1, "runtime-health", "服务存活与请求追踪", health)
        await self._case(1, "runtime-ready", "核心依赖就绪检查", readiness)
        await self._case(1, "runtime-metrics", "运行记录与指标汇总", run_metrics)

    async def _run_project_2(self, mode: AcceptanceMode) -> None:
        async def tools():
            body, _ = await self._request_json("GET", "/api/v1/tools")
            names = {item.get("name") for item in body}
            expected = {
                "search_products",
                "get_product",
                "check_inventory",
                "query_order",
            }
            missing = sorted(expected - names)
            if missing:
                raise AssertionError(f"缺少售前工具: {missing}")
            return (
                "passed",
                "商品、库存和订单工具均可发现",
                {"tool_count": len(names), "tools": sorted(names)},
            )

        async def evidence():
            body, _ = await self._request_json(
                "GET",
                "/api/v1/agents/runs?limit=20",
            )
            successful = [item for item in body if item.get("status") == "success"]
            if not successful:
                return "warning", "尚无成功运行记录", {"run_count": len(body)}
            return (
                "passed",
                "存在可查询的成功 Agent 运行证据",
                {
                    "run_count": len(body),
                    "successful_runs": len(successful),
                    "latest_run_id": successful[0].get("id"),
                },
            )

        async def active_multi_turn():
            first, _ = await self._request_json(
                "POST",
                "/api/v1/agents/presales/chat",
                json_body={"question": "请推荐一款适合油皮的商品"},
            )
            first_tools = [
                item.get("tool") for item in first.get("tool_calls", [])
            ]
            if "search_products" not in first_tools:
                raise AssertionError(f"首轮未调用商品搜索: {first_tools}")
            session_id = first.get("session_id")
            if not session_id:
                raise AssertionError("首轮没有返回 session_id")
            second, _ = await self._request_json(
                "POST",
                "/api/v1/agents/presales/chat",
                json_body={
                    "question": "那它现在有库存吗？",
                    "session_id": session_id,
                },
            )
            answer = str(second.get("answer", ""))
            if second.get("session_id") != session_id:
                raise AssertionError("第二轮没有沿用原会话")
            if "P1001" not in answer and "36" not in answer:
                raise AssertionError(f"追问没有正确继承商品上下文: {answer[:200]}")
            second_tools = [
                item.get("tool") for item in second.get("tool_calls", [])
            ]
            return (
                "passed",
                "真实大模型完成推荐并正确处理库存追问",
                {
                    "session_reused": True,
                    "first_tools": first_tools,
                    "second_tools": second_tools,
                    "first_duration_ms": first.get("duration_ms"),
                    "second_duration_ms": second.get("duration_ms"),
                },
            )

        await self._case(2, "presales-tools", "售前工具发现", tools)
        await self._case(2, "presales-evidence", "历史运行证据", evidence)
        if mode == "full":
            await self._case(
                2,
                "presales-multi-turn",
                "真实多轮商品推荐与库存追问",
                active_multi_turn,
            )
        else:
            await self._skipped(
                2,
                "presales-multi-turn",
                "真实多轮商品推荐与库存追问",
                "quick 模式不产生新的大模型调用",
            )

    async def _run_project_3(self) -> None:
        async def catalog():
            body, _ = await self._request_json(
                "GET",
                "/api/v1/data-platform/catalog",
            )
            assets = body.get("assets", [])
            names = {item.get("name") for item in assets}
            expected = {
                "commerce.products",
                "commerce.inventory",
                "commerce.orders",
                "ai_core.operational",
                "knowledge_base.commerce",
            }
            if not expected.issubset(names):
                raise AssertionError(f"数据目录不完整: {sorted(names)}")
            return (
                "passed",
                "业务数据、运行数据和知识库已统一登记",
                {"total_assets": body.get("total_assets"), "assets": sorted(names)},
            )

        async def quality():
            body, _ = await self._request_json(
                "GET",
                "/api/v1/data-platform/quality/commerce",
            )
            if body.get("failed_checks") != 0:
                raise AssertionError(f"数据质量存在失败项: {body}")
            return (
                "passed",
                "电商数据通过全部质量规则",
                {
                    "quality_score": body.get("quality_score"),
                    "passed_checks": body.get("passed_checks"),
                    "failed_checks": body.get("failed_checks"),
                },
            )

        async def releases_and_cache():
            releases, _ = await self._request_json(
                "GET",
                "/api/v1/data-platform/releases/commerce",
            )
            cache, _ = await self._request_json(
                "GET",
                "/api/v1/data-platform/cache/commerce",
            )
            required_cache = {"size", "hits", "misses", "hit_rate"}
            if not required_cache.issubset(cache):
                raise AssertionError("缓存指标字段不完整")
            active = [item for item in releases if item.get("is_active")]
            status: CaseStatus = "passed" if active else "warning"
            summary = (
                "版本发布历史、当前激活版本和缓存指标均可查询"
                if active
                else "缓存指标可查询，但尚无激活的数据发布版本"
            )
            return (
                status,
                summary,
                {
                    "release_count": len(releases),
                    "active_release_count": len(active),
                    "cache": {
                        key: cache.get(key)
                        for key in ("size", "hits", "misses", "hit_rate")
                    },
                },
            )

        await self._case(3, "data-catalog", "统一数据资产目录", catalog)
        await self._case(3, "data-quality", "八项数据质量检查", quality)
        await self._case(
            3,
            "data-release-cache",
            "数据版本与缓存观测",
            releases_and_cache,
        )

    async def _run_project_4(self, mode: AcceptanceMode) -> None:
        active_pipeline_completed = False

        async def history():
            body, _ = await self._request_json(
                "GET",
                "/api/v1/agents/live-clips/pipelines?limit=20",
            )
            succeeded = [
                item
                for item in body
                if item.get("status") == "succeeded"
                and item.get("stage") == "completed"
            ]
            if not succeeded:
                if active_pipeline_completed:
                    return (
                        "passed",
                        "隔离冒烟未污染业务任务表，本轮完整切片证据已生成",
                        {
                            "pipeline_count": len(body),
                            "isolated_smoke_completed": True,
                        },
                    )
                return (
                    "warning",
                    "当前数据库暂无完成的直播切片任务证据",
                    {"pipeline_count": len(body)},
                )
            latest = succeeded[0]
            return (
                "passed",
                "存在自动转写并完成物理切片的历史任务",
                {
                    "pipeline_count": len(body),
                    "latest_job_id": latest.get("id"),
                    "transcript_source": latest.get("transcript_source"),
                    "output_asset_count": len(
                        latest.get("output_asset_ids", [])
                    ),
                },
            )

        async def active_pipeline():
            nonlocal active_pipeline_completed
            result = await self._run_command(
                "test_live_clip_pipeline.py",
                [sys.executable, "scripts/test_live_clip_pipeline.py"],
                timeout_seconds=180,
            )
            stdout = result["stdout"]
            if '"status": "succeeded"' not in stdout:
                raise AssertionError(f"流水线未成功: {stdout[-1000:]}")
            payload = self._extract_last_json(stdout)
            if payload.get("stage") != "completed":
                raise AssertionError(f"任务阶段异常: {payload}")
            active_pipeline_completed = True
            return (
                "passed",
                "真实抽音频、规划、FFmpeg 切片和素材登记全部完成",
                {
                    "stage": payload.get("stage"),
                    "transcript_source": payload.get("transcript_source"),
                    "asr_provider": payload.get("asr_provider"),
                    "output_asset_count": payload.get("output_asset_count"),
                    "output_duration_seconds": payload.get(
                        "output_duration_seconds"
                    ),
                    "human_review_required": payload.get(
                        "human_review_required"
                    ),
                },
            )

        if mode == "full":
            await self._case(
                4,
                "live-clip-active",
                "直播回放自动转写与真实切片",
                active_pipeline,
            )
            await self._case(
                4,
                "live-clip-history",
                "异步切片历史证据",
                history,
            )
        else:
            await self._case(
                4,
                "live-clip-history",
                "异步切片历史证据",
                history,
            )
            await self._skipped(
                4,
                "live-clip-active",
                "直播回放自动转写与真实切片",
                "quick 模式不执行 FFmpeg 主动切片",
            )

    async def _run_project_5(self, mode: AcceptanceMode) -> None:
        async def history():
            jobs, _ = await self._request_json(
                "GET",
                "/api/v1/agents/content/jobs?limit=20",
            )
            drafts, _ = await self._request_json(
                "GET",
                "/api/v1/agents/content/drafts?limit=20",
            )
            succeeded = [item for item in jobs if item.get("status") == "succeeded"]
            if not succeeded or not drafts:
                return (
                    "warning",
                    "内容任务或草稿历史证据不足",
                    {
                        "job_count": len(jobs),
                        "succeeded_jobs": len(succeeded),
                        "draft_count": len(drafts),
                    },
                )
            return (
                "passed",
                "存在成功异步任务和可人工审核的内容草稿",
                {
                    "job_count": len(jobs),
                    "succeeded_jobs": len(succeeded),
                    "draft_count": len(drafts),
                },
            )

        async def active_job():
            job, _ = await self._request_json(
                "POST",
                "/api/v1/agents/content/jobs",
                expected_status=202,
                json_body={
                    "product_id": "P1001",
                    "platform": "xiaohongshu",
                    "tone": "friendly",
                },
                headers={"X-Idempotency-Key": f"acceptance-{self.run_id}"},
            )
            job_id = job.get("id")
            if not job_id:
                raise AssertionError("异步任务没有返回 job_id")
            final = await self._poll_job(
                f"/api/v1/agents/content/jobs/{job_id}",
                timeout_seconds=90,
            )
            if final.get("status") != "succeeded" or not final.get("draft_id"):
                raise AssertionError(f"内容任务未成功: {final}")
            draft, _ = await self._request_json(
                "GET",
                f"/api/v1/agents/content/drafts/{final['draft_id']}",
            )
            if not draft.get("human_review_required"):
                raise AssertionError("内容草稿没有进入人工审核门禁")
            return (
                "passed",
                "真实大模型生成异步完成并进入人工审核",
                {
                    "job_id": job_id,
                    "attempt_count": final.get("attempt_count"),
                    "draft_id": final.get("draft_id"),
                    "draft_status": draft.get("status"),
                    "human_review_required": draft.get(
                        "human_review_required"
                    ),
                },
            )

        await self._case(5, "content-history", "内容任务与草稿历史", history)
        if mode == "full":
            await self._case(
                5,
                "content-active",
                "异步内容生成与人工审核门禁",
                active_job,
            )
        else:
            await self._skipped(
                5,
                "content-active",
                "异步内容生成与人工审核门禁",
                "quick 模式不产生新的大模型调用",
            )

    async def _run_project_6(self) -> None:
        async def mcp_protocol():
            result = await self._run_command(
                "test_mcp_client.py",
                [sys.executable, "scripts/test_mcp_client.py"],
                timeout_seconds=60,
            )
            output = result["stdout"]
            required = [
                "MCP",
                "search_products",
                "check_inventory",
                "commerce://data-catalog",
            ]
            missing = [item for item in required if item not in output]
            if missing:
                raise AssertionError(f"MCP 输出缺少证据: {missing}")
            return (
                "passed",
                "真实 MCP 客户端完成工具发现、资源读取和库存调用",
                {
                    "tool_discovery": True,
                    "resource_read": True,
                    "tool_invoke": True,
                },
            )

        await self._case(
            6,
            "mcp-protocol",
            "MCP 协议级连接与能力调用",
            mcp_protocol,
        )

    async def _run_project_7(self) -> None:
        async def assets():
            body, _ = await self._request_json(
                "GET",
                "/api/v1/assets?limit=100",
            )
            items = body.get("items", [])
            if body.get("total") != len(items):
                raise AssertionError("素材 total 与实际返回数量不一致")
            if not items:
                return "warning", "素材中心当前为空", {"total": 0}
            missing_source = [item.get("id") for item in items if not item.get("source")]
            if missing_source:
                raise AssertionError(f"素材缺少来源字段: {missing_source[:5]}")
            types = sorted({item.get("asset_type") for item in items})
            sources = sorted({item.get("source") for item in items})
            return (
                "passed",
                "素材可检索且保留类型、商品和来源追踪",
                {
                    "total": body.get("total"),
                    "asset_types": types,
                    "source_count": len(sources),
                    "sources": sources[:10],
                },
            )

        await self._case(
            7,
            "asset-traceability",
            "多模态素材检索与来源追踪",
            assets,
        )

    async def _run_project_8(self, run_evaluation: bool) -> None:
        async def evaluation_history():
            body, _ = await self._request_json(
                "GET",
                "/api/v1/evaluations/presales/runs?limit=20",
            )
            if not body:
                return "warning", "尚无 Agent 评测历史", {"run_count": 0}
            latest = body[0]
            pass_rate = float(latest.get("pass_rate", 0))
            accuracy = float(latest.get("tool_selection_accuracy", 0))
            status: CaseStatus = (
                "passed"
                if pass_rate >= 90 and accuracy >= 90
                else "warning"
                if pass_rate >= 80 and accuracy >= 80
                else "failed"
            )
            return (
                status,
                f"最新评测通过率 {pass_rate}%，工具准确率 {accuracy}%",
                {
                    "run_id": latest.get("run_id"),
                    "suite_version": latest.get("suite_version"),
                    "total_cases": latest.get("total_cases"),
                    "pass_rate": pass_rate,
                    "tool_selection_accuracy": accuracy,
                    "p95_duration_ms": latest.get("p95_duration_ms"),
                },
            )

        async def alerts():
            body, _ = await self._request_json(
                "GET",
                "/api/v1/metrics/alerts",
            )
            alerts = body.get("alerts", [])
            if body.get("status") != "healthy" or alerts:
                return (
                    "warning",
                    f"当前存在 {len(alerts)} 项 HTTP 告警",
                    {
                        "status": body.get("status"),
                        "sample_size": body.get("sample_size"),
                        "alerts": alerts,
                    },
                )
            return (
                "passed",
                "HTTP 指标已采样且当前无触发告警",
                {
                    "sample_size": body.get("sample_size"),
                    "server_error_rate_percent": body.get(
                        "server_error_rate_percent"
                    ),
                },
            )

        async def active_evaluation():
            body, _ = await self._request_json(
                "POST",
                "/api/v1/evaluations/presales/run",
            )
            pass_rate = float(body.get("pass_rate", 0))
            accuracy = float(body.get("tool_selection_accuracy", 0))
            if pass_rate < 90 or accuracy < 90:
                raise AssertionError(
                    f"主动评测未达门槛: pass_rate={pass_rate}, "
                    f"tool_accuracy={accuracy}"
                )
            return (
                "passed",
                "当前代码重新执行固定评测并达到发布门槛",
                {
                    "run_id": body.get("run_id"),
                    "suite_version": body.get("suite_version"),
                    "total_cases": body.get("total_cases"),
                    "pass_rate": pass_rate,
                    "tool_selection_accuracy": accuracy,
                    "p95_duration_ms": body.get("p95_duration_ms"),
                },
            )

        await self._case(
            8,
            "evaluation-history",
            "固定评测集历史基线",
            evaluation_history,
        )
        await self._case(
            8,
            "observability-alerts",
            "HTTP 指标与告警检查",
            alerts,
        )
        if run_evaluation:
            await self._case(
                8,
                "evaluation-active",
                "主动执行当前版本固定评测",
                active_evaluation,
            )
        else:
            await self._skipped(
                8,
                "evaluation-active",
                "主动执行当前版本固定评测",
                "未指定 --run-evaluation，避免产生30条模型调用费用",
            )

    async def _skipped(
        self,
        project_id: int,
        case_id: str,
        name: str,
        reason: str,
    ) -> None:
        async def action():
            return "skipped", reason, {}

        await self._case(project_id, case_id, name, action)

    async def _poll_job(
        self,
        path: str,
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        latest: dict[str, Any] = {}
        while time.monotonic() < deadline:
            body, _ = await self._request_json("GET", path)
            if not isinstance(body, dict):
                raise AssertionError(f"任务接口返回类型错误: {type(body)}")
            latest = body
            if body.get("status") in {"succeeded", "failed"}:
                return body
            await asyncio.sleep(0.5)
        raise TimeoutError(f"等待异步任务超时，最后状态: {latest}")

    async def _run_command(
        self,
        name: str,
        command: list[str],
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(PROJECT_ROOT),
                env={
                    **os.environ,
                    **(
                        {"MCP_API_KEY": self.api_key}
                        if self.api_key
                        else {}
                    ),
                },
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            raise RuntimeError(f"无法启动 {name}: {error}") from error
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"{name} 执行超过 {timeout_seconds} 秒")
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise RuntimeError(
                f"{name} 返回 {process.returncode}: "
                f"{(stderr or stdout)[-1500:]}"
            )
        return {
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    @staticmethod
    def _extract_last_json(text: str) -> dict[str, Any]:
        starts = [index for index, char in enumerate(text) if char == "{"]
        for start in reversed(starts):
            try:
                payload = json.loads(text[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        raise AssertionError("命令输出中没有找到 JSON 结果")

    def _build_projects(self) -> list[AcceptanceProjectResult]:
        grouped: dict[int, list[AcceptanceCaseResult]] = defaultdict(list)
        for item in self.results:
            grouped[item.project_id].append(item)
        projects = []
        for project_id in sorted(PROJECT_NAMES):
            cases = grouped[project_id]
            failed = sum(item.status == "failed" for item in cases)
            warnings = sum(item.status == "warning" for item in cases)
            skipped = sum(item.status == "skipped" for item in cases)
            passed = sum(item.status == "passed" for item in cases)
            status: CaseStatus = (
                "failed"
                if failed
                else "warning"
                if warnings or skipped
                else "passed"
            )
            projects.append(
                AcceptanceProjectResult(
                    project_id=project_id,
                    name=PROJECT_NAMES[project_id],
                    status=status,
                    passed_cases=passed,
                    warning_cases=warnings,
                    failed_cases=failed,
                    skipped_cases=skipped,
                    cases=cases,
                )
            )
        return projects


def render_markdown_report(report: ArchitectureAcceptanceReport) -> str:
    status_text = {
        "passed": "通过",
        "passed_with_warnings": "通过，但存在待完善项",
        "failed": "未通过",
    }[report.status]
    lines = [
        "# 电商 AI 八项目架构验收报告",
        "",
        f"- 验收结论：**{status_text}**",
        f"- 运行编号：`{report.run_id}`",
        f"- 验收模式：`{report.mode}`",
        f"- 开始时间：{report.started_at}",
        f"- 总耗时：{report.duration_ms} ms",
        (
            f"- 用例：{report.total_cases} 项；通过 {report.passed_cases}；"
            f"警告 {report.warning_cases}；失败 {report.failed_cases}；"
            f"跳过 {report.skipped_cases}"
        ),
        f"- 已执行用例通过率：{report.pass_rate}%",
        "",
        "## 八项目结果",
        "",
        "| 项目 | 结论 | 通过 | 警告 | 失败 | 跳过 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    status_labels = {
        "passed": "通过",
        "warning": "待完善",
        "failed": "失败",
        "skipped": "跳过",
    }
    for project in report.projects:
        lines.append(
            f"| 项目{project.project_id} {project.name} | "
            f"{status_labels[project.status]} | {project.passed_cases} | "
            f"{project.warning_cases} | {project.failed_cases} | "
            f"{project.skipped_cases} |"
        )
    for project in report.projects:
        lines.extend(
            [
                "",
                f"## 项目{project.project_id}：{project.name}",
                "",
            ]
        )
        for case in project.cases:
            lines.extend(
                [
                    f"### [{status_labels[case.status]}] {case.name}",
                    "",
                    f"- 用例编号：`{case.case_id}`",
                    f"- 耗时：{case.duration_ms} ms",
                    f"- 结论：{case.summary}",
                ]
            )
            if case.error:
                lines.append(f"- 错误：`{case.error}`")
            if case.evidence:
                lines.extend(
                    [
                        "- 证据：",
                        "",
                        "```json",
                        json.dumps(
                            case.evidence,
                            ensure_ascii=False,
                            indent=2,
                            default=str,
                        ),
                        "```",
                    ]
                )
    lines.extend(
        [
            "",
            "## 结果解释",
            "",
            "- `通过`：该能力已实际执行并满足当前验收条件。",
            "- `待完善`：核心功能可用，但缺少可选配置或历史证据。",
            "- `失败`：接口、业务结果或质量门槛不符合预期。",
            "- `跳过`：当前模式主动跳过高耗时或会产生模型费用的检查。",
            "",
            "> 验收报告只证明本次环境与本次用例的结果，不能替代生产压测、"
            "真实用户验证和第三方服务 SLA。",
            "",
        ]
    )
    return "\n".join(lines)
