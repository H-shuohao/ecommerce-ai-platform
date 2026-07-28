import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.architecture_acceptance_service import (
    ArchitectureAcceptanceRunner,
    render_markdown_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="一键验收电商 AI 八项目架构并生成 JSON、Markdown 报告。",
    )
    parser.add_argument(
        "--mode",
        choices=("quick", "full"),
        default="quick",
        help="quick 只读检查；full 额外执行真实 LLM、异步任务和 FFmpeg 链路。",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="被验收服务的 HTTP 地址。",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ACCEPTANCE_API_KEY"),
        help="认证开启时使用的 admin API Key；推荐通过环境变量提供。",
    )
    parser.add_argument(
        "--run-evaluation",
        action="store_true",
        help="主动运行完整售前固定评测；会产生约30条模型调用。",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "data" / "acceptance-reports"),
        help="JSON 和 Markdown 报告输出目录。",
    )
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    runner = ArchitectureAcceptanceRunner(
        base_url=args.base_url,
        api_key=args.api_key,
        timeout_seconds=45,
    )
    print(
        f"开始执行八项目架构验收：mode={args.mode}, "
        f"run_evaluation={args.run_evaluation}",
        flush=True,
    )
    report = await runner.run(
        mode=args.mode,
        run_evaluation=args.run_evaluation,
    )
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    stem = f"architecture-acceptance-{timestamp}-{report.run_id[:8]}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(
            report.model_dump(),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_markdown_report(report),
        encoding="utf-8",
    )
    print("ARCHITECTURE_ACCEPTANCE_SUMMARY_START", flush=True)
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "status": report.status,
                "mode": report.mode,
                "total_cases": report.total_cases,
                "passed_cases": report.passed_cases,
                "warning_cases": report.warning_cases,
                "failed_cases": report.failed_cases,
                "skipped_cases": report.skipped_cases,
                "pass_rate": report.pass_rate,
                "duration_ms": report.duration_ms,
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    print("ARCHITECTURE_ACCEPTANCE_SUMMARY_END", flush=True)
    return 1 if report.failed_cases else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
