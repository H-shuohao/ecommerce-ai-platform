import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from database import database
from main import app
from services.rag_service import RagResult


class FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, *args, **kwargs):
        return SimpleNamespace(json=lambda: {"Result": "proxy-ok"})


class ApiBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.asset_ids_to_delete: list[str] = []

    def tearDown(self) -> None:
        if self.asset_ids_to_delete:
            with database.lock, database.connection:
                database.connection.executemany(
                    "DELETE FROM media_assets WHERE id = ?",
                    [(asset_id,) for asset_id in self.asset_ids_to_delete],
                )

    def test_health(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_demo_page(self) -> None:
        response = self.client.get("/demo")

        self.assertEqual(response.status_code, 200)
        self.assertIn("小懒 AI 导购", response.text)

    @patch.multiple(
        "app.api.health.settings",
        ARK_API_KEY="",
        ARK_ENDPOINT_ID="",
        VOLC_AK="",
        VOLC_SK="",
        VOLC_ACCOUNT_ID="",
    )
    def test_readiness_reports_missing_core_configuration(self) -> None:
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "not_ready")
        self.assertFalse(response.json()["components"]["llm"])
        self.assertFalse(response.json()["components"]["rag"])

    def test_search_products_by_keyword(self) -> None:
        response = self.client.get("/api/v1/products", params={"keyword": "油皮"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["id"], "P1001")

    def test_search_products_by_max_price(self) -> None:
        response = self.client.get("/api/v1/products", params={"max_price": 100})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["items"])
        self.assertTrue(all(item["price"] <= 100 for item in response.json()["items"]))

    def test_search_products_with_combined_keywords(self) -> None:
        response = self.client.get(
            "/api/v1/products",
            params={"keyword": "油皮防晒", "max_price": 150},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["id"], "P1001")

    def test_get_out_of_stock_inventory(self) -> None:
        response = self.client.get("/api/v1/products/P1002/inventory")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["quantity"], 0)
        self.assertFalse(response.json()["in_stock"])

    def test_get_order(self) -> None:
        response = self.client.get("/api/v1/orders/O20260720001")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "shipped")

    def test_missing_product_returns_404(self) -> None:
        response = self.client.get("/api/v1/products/UNKNOWN")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "商品不存在")

    def test_list_agent_tools(self) -> None:
        response = self.client.get("/api/v1/tools")

        self.assertEqual(response.status_code, 200)
        names = {tool["name"] for tool in response.json()}
        self.assertEqual(
            names,
            {
                "search_products", "get_product", "check_inventory", "query_order",
                "search_media_assets",
            },
        )

    def test_invoke_inventory_tool(self) -> None:
        response = self.client.post(
            "/api/v1/tools/check_inventory/invoke",
            json={"arguments": {"product_id": "P1002"}},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        inventory = response.json()["data"]["inventory"]
        self.assertEqual(inventory["quantity"], 0)
        self.assertFalse(inventory["in_stock"])

    def test_invoke_media_asset_search_tool(self) -> None:
        response = self.client.post(
            "/api/v1/tools/search_media_assets/invoke",
            json={"arguments": {"product_id": "P1001", "asset_type": "text"}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertIn("items", response.json()["data"])

    def test_tool_rejects_missing_required_argument(self) -> None:
        response = self.client.post(
            "/api/v1/tools/check_inventory/invoke",
            json={"arguments": {}},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("缺少必填参数", response.json()["detail"])

    def test_unknown_tool_returns_404(self) -> None:
        response = self.client.post(
            "/api/v1/tools/not_exists/invoke",
            json={"arguments": {}},
        )

        self.assertEqual(response.status_code, 404)

    def test_agent_metrics_route(self) -> None:
        response = self.client.get("/api/v1/agents/runs/metrics")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("total_runs", body)
        self.assertIn("success_rate", body)
        self.assertIn("average_duration_ms", body)
        self.assertIn("tool_usage", body)

    def test_list_presales_evaluation_cases(self) -> None:
        response = self.client.get("/api/v1/evaluations/presales/cases")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 4)
        self.assertIn("expected_tools", response.json()[0])

    def test_list_presales_evaluation_history(self) -> None:
        response = self.client.get("/api/v1/evaluations/presales/runs")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_data_platform_catalog(self) -> None:
        response = self.client.get("/api/v1/data-platform/catalog")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_assets"], 5)
        names = {asset["name"] for asset in response.json()["assets"]}
        self.assertIn("commerce.products", names)
        self.assertIn("ai_core.operational", names)

    def test_commerce_data_quality_is_clean(self) -> None:
        response = self.client.get("/api/v1/data-platform/quality/commerce")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["quality_score"], 100.0)
        self.assertEqual(response.json()["failed_checks"], 0)

    def test_list_commerce_data_releases(self) -> None:
        response = self.client.get("/api/v1/data-platform/releases/commerce")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_staging_quality_detects_negative_inventory_without_persisting(self) -> None:
        candidate = {
            "products": [
                {
                    "id": "P1",
                    "name": "测试商品",
                    "category": "测试",
                    "brand": "测试品牌",
                    "price": 10,
                    "description": "测试描述",
                    "tags": [],
                }
            ],
            "inventory": {"P1": -3},
            "orders": [],
        }

        response = self.client.post(
            "/api/v1/data-platform/staging/commerce/validate",
            json={"data": candidate},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ready_to_publish"])
        self.assertFalse(response.json()["persisted"])
        failed = {
            item["name"]
            for item in response.json()["quality_report"]["checks"]
            if not item["passed"]
        }
        self.assertIn("库存数量非负", failed)

    @patch("services.content_agent_service.llm_service.complete")
    def test_content_agent_generates_auditable_draft(self, complete) -> None:
        complete.return_value = (
            '{"title":"通勤防晒轻体验",'
            '"body":"清爽防晒乳轻薄不黏腻，适合油性和混合性肤质。",'
            '"hashtags":["#防晒","油皮"]}'
        )

        response = self.client.post(
            "/api/v1/agents/content/generate",
            json={
                "product_id": "P1001",
                "platform": "xiaohongshu",
                "tone": "friendly",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["product_id"], "P1001")
        self.assertEqual(body["hashtags"], ["防晒", "油皮"])
        self.assertTrue(body["human_review_required"])
        self.assertEqual(body["status"], "pending")
        self.assertTrue(body["draft_id"])
        self.assertEqual(body["source_facts"]["price"], 129.0)

        review = self.client.post(
            f"/api/v1/agents/content/drafts/{body['draft_id']}/review",
            json={"action": "approved", "comment": "人工核验通过"},
        )
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.json()["status"], "approved")
        self.assertFalse(review.json()["human_review_required"])

        assets = self.client.get(
            "/api/v1/assets",
            params={"product_id": "P1001", "asset_type": "text", "tag": "xiaohongshu"},
        )
        self.assertEqual(assets.status_code, 200)
        matching = [
            item for item in assets.json()["items"]
            if item["uri"] == f"content-draft://{body['draft_id']}"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["source"], "content-agent-approved")
        self.asset_ids_to_delete.append(matching[0]["id"])

    def test_content_agent_rejects_unknown_product(self) -> None:
        response = self.client.post(
            "/api/v1/agents/content/generate",
            json={
                "product_id": "UNKNOWN",
                "platform": "douyin",
                "tone": "energetic",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "商品不存在: UNKNOWN")

    @patch("services.content_agent_service.llm_service.complete")
    def test_high_risk_content_cannot_be_approved(self, complete) -> None:
        complete.return_value = (
            '{"title":"清爽通勤防晒",'
            '"body":"质地轻薄不黏腻。",'
            '"hashtags":["护肤"]}'
        )
        generated = self.client.post(
            "/api/v1/agents/content/generate",
            json={
                "product_id": "P1001",
                "platform": "xiaohongshu",
                "tone": "friendly",
            },
        )
        draft_id = generated.json()["draft_id"]

        edited = self.client.patch(
            f"/api/v1/agents/content/drafts/{draft_id}",
            json={
                "title": "百分百有效",
                "body": "这款商品可以根治皮肤问题。",
            },
        )

        compliance = self.client.get(
            f"/api/v1/agents/content/drafts/{draft_id}/compliance"
        )
        review = self.client.post(
            f"/api/v1/agents/content/drafts/{draft_id}/review",
            json={"action": "approved", "comment": "尝试批准"},
        )

        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["status"], "pending")
        self.assertEqual(compliance.status_code, 200)
        self.assertFalse(compliance.json()["passed"])
        self.assertEqual(compliance.json()["risk_level"], "high")
        self.assertEqual(review.status_code, 409)
        self.assertIn("不能批准", review.json()["detail"])

    @patch("services.presales_agent_service.llm_service.complete")
    @patch(
        "services.presales_agent_service.rag_service.retrieve_result",
        new_callable=AsyncMock,
    )
    @patch("app.api.agents.agent_run_repository.record", return_value="run-test")
    def test_presales_agent_selects_inventory_tool(
        self,
        record_run,
        retrieve: AsyncMock,
        complete,
    ) -> None:
        complete.side_effect = [
            '{"tool":"check_inventory","arguments":{"product_id":"P1002"}}',
            '{"tool":"null","arguments":{}}',
            "P1002 当前无库存。",
        ]
        retrieve.return_value = RagResult(reason="no_result")

        response = self.client.post(
            "/api/v1/agents/presales/chat",
            json={"question": "P1002 现在有库存吗？"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "P1002 当前无库存。")
        self.assertEqual(response.json()["tool_calls"][0]["tool"], "check_inventory")
        inventory = response.json()["tool_calls"][0]["result"]["inventory"]
        self.assertEqual(inventory["quantity"], 0)
        self.assertFalse(response.json()["rag_used"])
        self.assertEqual(complete.call_count, 3)
        self.assertEqual(response.json()["run_id"], "run-test")
        record_run.assert_called_once()

    @patch("services.presales_agent_service.llm_service.complete")
    @patch(
        "services.presales_agent_service.rag_service.retrieve_result",
        new_callable=AsyncMock,
    )
    @patch("app.api.agents.agent_run_repository.record", return_value="run-test")
    def test_presales_agent_runs_search_then_inventory(
        self,
        record_run,
        retrieve: AsyncMock,
        complete,
    ) -> None:
        complete.side_effect = [
            '{"tool":"search_products","arguments":{"keyword":"油皮"}}',
            '{"tool":"check_inventory","arguments":{"product_id":"P1001"}}',
            '{"tool":null,"arguments":{}}',
            "推荐 P1001，适合油皮且当前有库存。",
        ]
        retrieve.return_value = RagResult(reason="no_result")

        response = self.client.post(
            "/api/v1/agents/presales/chat",
            json={"question": "推荐适合油皮并且有库存的商品"},
        )

        self.assertEqual(response.status_code, 200)
        calls = response.json()["tool_calls"]
        self.assertEqual([call["tool"] for call in calls], ["search_products", "check_inventory"])
        self.assertEqual(calls[0]["result"]["items"][0]["id"], "P1001")
        self.assertEqual(calls[1]["result"]["inventory"]["quantity"], 36)
        self.assertEqual(complete.call_count, 4)
        record_run.assert_called_once()

    @patch("services.presales_agent_service.llm_service.complete")
    @patch(
        "services.presales_agent_service.rag_service.retrieve_result",
        new_callable=AsyncMock,
    )
    @patch("app.api.agents.agent_run_repository.record", return_value="run-memory")
    def test_inventory_follow_up_refreshes_dynamic_data(
        self,
        record_run,
        retrieve: AsyncMock,
        complete,
    ) -> None:
        complete.return_value = "P1001 当前库存为 36 件。"
        retrieve.return_value = RagResult(reason="no_result")

        from services.conversation_repository import conversation_repository

        conversation_repository.append_exchange(
            "inventory-memory-test",
            "请介绍这个商品",
            "为您推荐一款清爽防晒乳。",
        )
        conversation_repository.set_current_product_id(
            "inventory-memory-test",
            "P1001",
        )
        response = self.client.post(
            "/api/v1/agents/presales/chat",
            json={
                "question": "那它现在有库存吗？",
                "session_id": "inventory-memory-test",
            },
        )

        self.assertEqual(response.status_code, 200)
        calls = response.json()["tool_calls"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "check_inventory")
        self.assertEqual(calls[0]["arguments"]["product_id"], "P1001")
        self.assertEqual(calls[0]["result"]["inventory"]["quantity"], 36)
        self.assertEqual(complete.call_count, 1)

        session = self.client.get(
            "/api/v1/agents/sessions/inventory-memory-test"
        ).json()
        self.assertEqual(session["current_product_id"], "P1001")

    @patch("app.api.rtc.build_rtc_token", return_value="test-rtc-token")
    def test_get_scenes_returns_rtc_configuration(self, build_token) -> None:
        response = self.client.post("/getScenes")

        self.assertEqual(response.status_code, 200)
        scene = response.json()["Result"]["scenes"][0]
        self.assertEqual(scene["rtc"]["Token"], "test-rtc-token")
        self.assertEqual(scene["scene"]["id"], "Custom")
        build_token.assert_called_once()

    @patch("app.api.rtc.Signer")
    @patch("app.api.rtc.httpx.AsyncClient", FakeAsyncClient)
    @patch("app.api.rtc.require_setting", side_effect=lambda value, name: value or name)
    def test_proxy_forwards_stop_voice_chat(self, require_setting, signer) -> None:
        response = self.client.post("/proxy?Action=StopVoiceChat")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"Result": "proxy-ok"})
        signer.assert_called_once()

    @patch("app.api.rtc.llm_service.chat_stream")
    @patch("app.api.rtc.rag_service.retrieve_result", new_callable=AsyncMock)
    def test_chat_callback_streams_rag_llm_response(
        self,
        retrieve: AsyncMock,
        chat_stream,
    ) -> None:
        retrieve.return_value = RagResult(
            context="语音商品知识",
            score=0.91,
            relevant=True,
            reason="relevant",
        )
        chunk = SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="语音回答"))],
            usage=None,
            model_dump_json=lambda: '{"answer":"语音回答"}',
        )
        chat_stream.return_value = iter([chunk])

        response = self.client.post(
            "/api/chat_callback",
            json={"messages": [{"role": "user", "content": "语音问题"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('data: {"answer":"语音回答"}', response.text)
        self.assertIn("data: [DONE]", response.text)
        retrieve.assert_awaited_once_with("语音问题")
        chat_stream.assert_called_once_with(
            [{"role": "user", "content": "语音问题"}],
            "语音商品知识",
        )

    def test_debug_rag_requires_query(self) -> None:
        response = self.client.get("/debug/rag")

        self.assertEqual(response.status_code, 422)

    @patch("app.api.debug.rag_service.retrieve_result", new_callable=AsyncMock)
    def test_debug_rag_returns_retrieval_result(self, retrieve: AsyncMock) -> None:
        retrieve.return_value = RagResult(
            context="商品知识",
            score=0.88,
            relevant=True,
            reason="relevant",
        )

        response = self.client.get("/debug/rag", params={"query": "测试商品"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["retrieved_context"], "商品知识")
        self.assertEqual(response.json()["status"], "success")
        retrieve.assert_awaited_once_with("测试商品")

    @patch("app.api.debug.llm_service.chat_stream")
    @patch("app.api.debug.rag_service.retrieve_result", new_callable=AsyncMock)
    def test_debug_chat_json_combines_rag_and_llm(
        self,
        retrieve: AsyncMock,
        chat_stream,
    ) -> None:
        retrieve.return_value = RagResult(
            context="商品知识",
            score=0.88,
            relevant=True,
            reason="relevant",
        )
        chat_stream.return_value = iter(
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(delta=SimpleNamespace(content="推荐商品A"))
                    ],
                    usage=None,
                )
            ]
        )

        response = self.client.post(
            "/debug/chat/json",
            json={"history": [], "question": "请推荐商品"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "推荐商品A")
        retrieve.assert_awaited_once_with("请推荐商品")
        chat_stream.assert_called_once_with(
            [{"role": "user", "content": "请推荐商品"}],
            "商品知识",
        )


    def test_create_and_filter_multimodal_asset(self) -> None:
        unique_uri = f"https://assets.example.com/test-{uuid.uuid4()}.jpg"
        created = self.client.post(
            "/api/v1/assets",
            json={
                "asset_type": "image",
                "title": "P1001 通勤场景图",
                "uri": unique_uri,
                "product_id": "P1001",
                "source": "content-agent",
                "tags": ["通勤", "防晒", "通勤"],
            },
        )
        self.assertEqual(created.status_code, 201)
        asset = created.json()
        self.asset_ids_to_delete.append(asset["id"])
        self.assertEqual(asset["product_id"], "P1001")
        self.assertEqual(asset["tags"], ["通勤", "防晒"])

        listed = self.client.get(
            "/api/v1/assets",
            params={"product_id": "P1001", "asset_type": "image", "tag": "通勤"},
        )
        self.assertEqual(listed.status_code, 200)
        matching_ids = {item["id"] for item in listed.json()["items"]}
        self.assertIn(asset["id"], matching_ids)

        detail = self.client.get(f"/api/v1/assets/{asset['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["uri"], asset["uri"])

    def test_multimodal_asset_rejects_unknown_product(self) -> None:
        response = self.client.post(
            "/api/v1/assets",
            json={
                "asset_type": "video",
                "title": "不存在商品的视频",
                "uri": "https://assets.example.com/missing.mp4",
                "product_id": "P9999",
                "tags": [],
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("P9999", response.json()["detail"])

    @patch("services.live_clip_agent_service.llm_service.complete")
    def test_live_clip_agent_plans_and_registers_video_asset(self, complete) -> None:
        complete.return_value = (
            '{"clips":[{"title":"轻薄防晒卖点",'
            '"start_seconds":12,"end_seconds":28,'
            '"reason":"主播完整介绍了适用肤质和使用场景"}]}'
        )
        video_uri = f"https://assets.example.com/live-{uuid.uuid4()}.mp4"
        response = self.client.post(
            "/api/v1/agents/live-clips/plan",
            json={
                "product_id": "P1001",
                "video_uri": video_uri,
                "max_clips": 2,
                "transcript": [
                    {"start_seconds": 0, "end_seconds": 12, "text": "今天介绍一款防晒。"},
                    {"start_seconds": 12, "end_seconds": 28, "text": "它轻薄不黏腻，适合油性和混合性肤质日常通勤。"},
                    {"start_seconds": 28, "end_seconds": 35, "text": "接下来介绍使用方法。"},
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["physical_cut_completed"])
        self.assertTrue(body["human_review_required"])
        self.assertEqual(len(body["clips"]), 1)
        self.asset_ids_to_delete.append(body["clips"][0]["asset_id"])
        self.assertEqual(body["clips"][0]["clip_uri"], f"{video_uri}#t=12,28")

        asset = self.client.get(f"/api/v1/assets/{body['clips'][0]['asset_id']}")
        self.assertEqual(asset.status_code, 200)
        self.assertEqual(asset.json()["source"], "live-clip-agent")

    @patch("services.live_clip_agent_service.llm_service.complete")
    def test_live_clip_agent_rejects_out_of_range_plan(self, complete) -> None:
        complete.return_value = (
            '{"clips":[{"title":"越界片段","start_seconds":0,'
            '"end_seconds":99,"reason":"测试越界"}]}'
        )
        response = self.client.post(
            "/api/v1/agents/live-clips/plan",
            json={
                "product_id": "P1001",
                "video_uri": "https://assets.example.com/range-test.mp4",
                "transcript": [
                    {"start_seconds": 0, "end_seconds": 10, "text": "十秒转写内容"}
                ],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("超出转写范围", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
