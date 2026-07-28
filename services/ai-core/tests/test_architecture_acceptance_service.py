import json
import unittest

import httpx

from services.architecture_acceptance_service import (
    ArchitectureAcceptanceRunner,
    render_markdown_report,
)


class StubAcceptanceRunner(ArchitectureAcceptanceRunner):
    async def _run_command(
        self,
        name: str,
        command: list[str],
        *,
        timeout_seconds: float,
    ) -> dict:
        return {
            "returncode": 0,
            "stdout": (
                "MCP连接成功\n"
                "可用工具: ['search_products', 'check_inventory']\n"
                "Available resources: ['commerce://data-catalog']\n"
            ),
            "stderr": "",
        }


class ArchitectureAcceptanceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_quick_acceptance_maps_all_eight_projects(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            payloads = {
                "/health": {
                    "status": "ok",
                    "service": "test-service",
                },
                "/ready": {
                    "status": "ready",
                    "components": {
                        "llm": True,
                        "rag": True,
                        "rtc": True,
                        "batch_asr": True,
                    },
                },
                "/api/v1/agents/runs/metrics": {
                    "total_runs": 10,
                    "success_rate": 100,
                    "average_duration_ms": 100,
                },
                "/api/v1/tools": [
                    {"name": "search_products"},
                    {"name": "get_product"},
                    {"name": "check_inventory"},
                    {"name": "query_order"},
                ],
                "/api/v1/agents/runs": [
                    {"id": "run-1", "status": "success"},
                ],
                "/api/v1/data-platform/catalog": {
                    "total_assets": 5,
                    "assets": [
                        {"name": "commerce.products"},
                        {"name": "commerce.inventory"},
                        {"name": "commerce.orders"},
                        {"name": "ai_core.operational"},
                        {"name": "knowledge_base.commerce"},
                    ],
                },
                "/api/v1/data-platform/quality/commerce": {
                    "quality_score": 100,
                    "passed_checks": 8,
                    "failed_checks": 0,
                },
                "/api/v1/data-platform/releases/commerce": [
                    {"id": "release-1", "is_active": True},
                ],
                "/api/v1/data-platform/cache/commerce": {
                    "size": 1,
                    "hits": 2,
                    "misses": 1,
                    "hit_rate": 66.67,
                },
                "/api/v1/agents/live-clips/pipelines": [
                    {
                        "id": "clip-1",
                        "status": "succeeded",
                        "stage": "completed",
                        "transcript_source": "asr",
                        "output_asset_ids": ["asset-1"],
                    },
                ],
                "/api/v1/agents/content/jobs": [
                    {"id": "content-1", "status": "succeeded"},
                ],
                "/api/v1/agents/content/drafts": [
                    {"draft_id": "draft-1", "status": "pending"},
                ],
                "/api/v1/assets": {
                    "items": [
                        {
                            "id": "asset-1",
                            "asset_type": "video",
                            "source": "live-clip-agent",
                        }
                    ],
                    "total": 1,
                },
                "/api/v1/evaluations/presales/runs": [
                    {
                        "run_id": "eval-1",
                        "suite_version": "v3",
                        "total_cases": 30,
                        "pass_rate": 100,
                        "tool_selection_accuracy": 100,
                        "p95_duration_ms": 1000,
                    }
                ],
                "/api/v1/metrics/alerts": {
                    "status": "healthy",
                    "sample_size": 100,
                    "server_error_rate_percent": 0,
                    "alerts": [],
                },
            }
            payload = payloads.get(path)
            if payload is None:
                return httpx.Response(404, json={"detail": path})
            return httpx.Response(
                200,
                json=payload,
                headers={"X-Request-ID": "request-test"},
            )

        client = httpx.AsyncClient(
            base_url="http://test",
            transport=httpx.MockTransport(handler),
        )
        runner = StubAcceptanceRunner(
            base_url="http://test",
            client=client,
        )
        report = await runner.run(mode="quick")
        await client.aclose()

        self.assertEqual(len(report.projects), 8)
        self.assertEqual(report.failed_cases, 0)
        self.assertEqual(report.status, "passed_with_warnings")
        self.assertEqual(report.total_cases, 18)
        self.assertEqual(
            {project.project_id for project in report.projects},
            set(range(1, 9)),
        )
        markdown = render_markdown_report(report)
        self.assertIn("电商 AI 八项目架构验收报告", markdown)
        self.assertIn("项目6 MCP 共享层", markdown)

    def test_extract_last_json_ignores_prefix_logs(self):
        payload = {"status": "succeeded", "stage": "completed"}
        text = "some logs\n" + json.dumps(payload, ensure_ascii=False)
        self.assertEqual(
            ArchitectureAcceptanceRunner._extract_last_json(text),
            payload,
        )


if __name__ == "__main__":
    unittest.main()
