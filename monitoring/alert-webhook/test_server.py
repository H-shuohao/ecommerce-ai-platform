import unittest
from pathlib import Path

import server


class AlertWebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_data_file = server.DATA_FILE
        self.test_data_file = Path(__file__).with_name(".test-alerts.jsonl")
        self.test_data_file.unlink(missing_ok=True)
        server.DATA_FILE = self.test_data_file

    def tearDown(self) -> None:
        server.DATA_FILE = self.original_data_file
        self.test_data_file.unlink(missing_ok=True)

    def test_store_and_read_event(self) -> None:
        server.store_event(
            {
                "status": "firing",
                "receiver": "local-webhook",
                "commonLabels": {
                    "alertname": "AIServiceDown",
                    "severity": "critical",
                },
                "alerts": [{"status": "firing"}],
            }
        )

        events = server.read_events()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "firing")
        self.assertEqual(
            events[0]["common_labels"]["alertname"],
            "AIServiceDown",
        )

    def test_html_page_escapes_alert_content(self) -> None:
        page = server.render_page(
            [
                {
                    "received_at": "2026-07-26T00:00:00+00:00",
                    "status": "firing",
                    "common_labels": {
                        "alertname": "<script>alert(1)</script>",
                        "severity": "critical",
                    },
                }
            ]
        ).decode("utf-8")

        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


if __name__ == "__main__":
    unittest.main()
