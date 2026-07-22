import unittest
import logging

from fastapi.testclient import TestClient

from main import app


class McpServerTests(unittest.TestCase):
    def test_initialize_and_list_shared_commerce_tools(self) -> None:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        with TestClient(app) as client:
            initialized = client.post(
                "/mcp/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.0"},
                    },
                },
            )
            self.assertEqual(initialized.status_code, 200)
            self.assertEqual(
                initialized.json()["result"]["serverInfo"]["name"],
                "ecommerce-ai-tools",
            )

            listed = client.post(
                "/mcp/",
                headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                },
            )
            self.assertEqual(listed.status_code, 200)
            names = {
                tool["name"]
                for tool in listed.json()["result"]["tools"]
            }
            self.assertEqual(
                names,
                {
                    "search_products", "get_product", "check_inventory", "query_order",
                    "search_media_assets",
                },
            )

            resources = client.post(
                "/mcp/",
                headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "resources/list",
                    "params": {},
                },
            )
            self.assertEqual(resources.status_code, 200)
            resource_uris = {
                item["uri"] for item in resources.json()["result"]["resources"]
            }
            self.assertIn("commerce://data-catalog", resource_uris)

            catalog = client.post(
                "/mcp/",
                headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "resources/read",
                    "params": {"uri": "commerce://data-catalog"},
                },
            )
            self.assertEqual(catalog.status_code, 200)
            catalog_text = catalog.json()["result"]["contents"][0]["text"]
            self.assertIn('"total_assets": 5', catalog_text)
            self.assertIn("commerce.products", catalog_text)

            prompts = client.post(
                "/mcp/",
                headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
                json={
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "prompts/list",
                    "params": {},
                },
            )
            self.assertEqual(prompts.status_code, 200)
            prompt_names = {
                item["name"] for item in prompts.json()["result"]["prompts"]
            }
            self.assertIn("presales_assistant", prompt_names)

            prompt = client.post(
                "/mcp/",
                headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
                json={
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "prompts/get",
                    "params": {
                        "name": "presales_assistant",
                        "arguments": {"customer_question": "请查询 P1002 库存"},
                    },
                },
            )
            self.assertEqual(prompt.status_code, 200)
            prompt_text = prompt.json()["result"]["messages"][0]["content"]["text"]
            self.assertIn("check_inventory", prompt_text)
            self.assertIn("P1002", prompt_text)

            called = client.post(
                "/mcp/",
                headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
                json={
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "check_inventory",
                        "arguments": {"product_id": "P1002"},
                    },
                },
            )
            self.assertEqual(called.status_code, 200)
            result = called.json()["result"]
            self.assertFalse(result.get("isError", False))
            self.assertIn("P1002", result["content"][0]["text"])
            self.assertIn('"quantity": 0', result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
