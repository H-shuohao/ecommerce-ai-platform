import json
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class AgentStreamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @patch(
        "services.presales_agent_service.llm_service.complete_stream",
        return_value=iter(["P1002", " 当前无库存。"]),
    )
    @patch(
        "services.presales_agent_service.llm_service.complete",
        return_value='{"tool":"check_inventory","arguments":{"product_id":"P1002"}}',
    )
    @patch("app.api.agents.agent_run_repository.record", return_value="stream-run")
    def test_stream_returns_status_tools_deltas_and_done(
        self,
        record_run,
        complete,
        complete_stream,
    ) -> None:
        session_id = f"stream-{uuid.uuid4()}"

        response = self.client.post(
            "/api/v1/agents/presales/chat/stream",
            json={
                "question": "P1002现在有库存吗？",
                "session_id": session_id,
            },
        )
        events = [
            json.loads(line)
            for line in response.text.splitlines()
            if line.strip()
        ]

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["content-type"].startswith("application/x-ndjson")
        )
        self.assertEqual(
            [event["event"] for event in events],
            ["session", "status", "tool", "delta", "delta", "done"],
        )
        self.assertEqual(events[2]["tool"], "check_inventory")
        self.assertEqual(events[-1]["answer"], "P1002 当前无库存。")
        self.assertEqual(events[-1]["run_id"], "stream-run")
        self.assertEqual(events[-1]["session_id"], session_id)
        self.assertEqual(events[-1]["tool_calls"][0]["tool"], "check_inventory")
        complete.assert_not_called()
        complete_stream.assert_called_once()
        record_run.assert_called_once()

    @patch("services.presales_agent_service.llm_service.complete_stream")
    @patch(
        "services.presales_agent_service.llm_service.complete",
        return_value="模型没有按要求返回 JSON",
    )
    @patch("app.api.agents.agent_run_repository.record", return_value="failed-run")
    def test_stream_reports_runtime_error_as_final_event(
        self,
        record_run,
        complete,
        complete_stream,
    ) -> None:
        response = self.client.post(
            "/api/v1/agents/presales/chat/stream",
            json={"question": "查询一个商品"},
        )
        events = [
            json.loads(line)
            for line in response.text.splitlines()
            if line.strip()
        ]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[-1]["event"], "error")
        self.assertEqual(events[-1]["code"], "AGENT_EXECUTION_FAILED")
        self.assertIn("有效 JSON", events[-1]["message"])
        complete_stream.assert_not_called()
        self.assertEqual(record_run.call_args.kwargs["status"], "failed")
