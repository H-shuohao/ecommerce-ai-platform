import html
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "9087"))
DATA_FILE = Path(os.getenv("ALERT_DATA_FILE", "/data/alerts.jsonl"))
FILE_LOCK = threading.Lock()


def read_events(limit: int = 100) -> list[dict]:
    if not DATA_FILE.exists():
        return []
    with FILE_LOCK:
        lines = DATA_FILE.read_text(encoding="utf-8").splitlines()
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(events))


def store_event(payload: dict) -> dict:
    event = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "status": payload.get("status", "unknown"),
        "receiver": payload.get("receiver"),
        "group_labels": payload.get("groupLabels", {}),
        "common_labels": payload.get("commonLabels", {}),
        "alerts": payload.get("alerts", []),
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with FILE_LOCK:
        with DATA_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def render_page(events: list[dict]) -> bytes:
    cards = []
    for event in events:
        labels = event.get("common_labels", {})
        alert_name = labels.get("alertname", "unknown")
        severity = labels.get("severity", "unknown")
        cards.append(
            "<article>"
            f"<strong>{html.escape(alert_name)}</strong>"
            f"<span class='{html.escape(event['status'])}'>"
            f"{html.escape(event['status'])}</span>"
            f"<p>级别：{html.escape(severity)}　"
            f"接收时间：{html.escape(event['received_at'])}</p>"
            f"<pre>{html.escape(json.dumps(event, ensure_ascii=False, indent=2))}</pre>"
            "</article>"
        )
    empty = "<p>暂时没有收到告警。完成一次故障演练后再刷新页面。</p>"
    body = "".join(cards) or empty
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Platform 告警收件箱</title>
  <style>
    body {{ max-width: 960px; margin: 40px auto; padding: 0 20px;
            font-family: system-ui, sans-serif; background: #f4f7f5; color: #15231d; }}
    header {{ display: flex; align-items: baseline; justify-content: space-between; }}
    article {{ background: white; border: 1px solid #d9e4de; border-radius: 14px;
               padding: 18px; margin: 16px 0; }}
    span {{ margin-left: 12px; padding: 3px 9px; border-radius: 999px; color: white; }}
    .firing {{ background: #c83b3b; }} .resolved {{ background: #27815f; }}
    pre {{ overflow: auto; background: #f6f8f7; padding: 12px; border-radius: 8px; }}
  </style>
</head>
<body>
  <header><h1>AI Platform 告警收件箱</h1><small>最近 {len(events)} 条</small></header>
  <p>Alertmanager 分组、去重后发送到这里；页面刷新即可查看最新记录。</p>
  {body}
</body>
</html>""".encode("utf-8")


class AlertHandler(BaseHTTPRequestHandler):
    def send_content(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            content = json.dumps({"status": "ok"}).encode()
            self.send_content(200, content, "application/json")
            return
        if path == "/api/alerts":
            events = read_events()
            content = json.dumps(
                {"total": len(events), "items": events},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_content(200, content, "application/json; charset=utf-8")
            return
        if path == "/":
            self.send_content(
                200,
                render_page(read_events()),
                "text/html; charset=utf-8",
            )
            return
        self.send_content(404, b'{"detail":"not found"}', "application/json")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/alerts":
            self.send_content(404, b'{"detail":"not found"}', "application/json")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            event = store_event(payload)
        except (ValueError, json.JSONDecodeError):
            self.send_content(400, b'{"detail":"invalid json"}', "application/json")
            return
        content = json.dumps(event, ensure_ascii=False).encode("utf-8")
        self.send_content(202, content, "application/json; charset=utf-8")

    def log_message(self, format: str, *args: object) -> None:
        print(f"[alert-webhook] {self.address_string()} {format % args}")


if __name__ == "__main__":
    print(f"Alert webhook listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), AlertHandler).serve_forever()
