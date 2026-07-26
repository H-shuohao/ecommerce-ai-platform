import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.evaluation_service import evaluation_service


async def main() -> None:
    print("开始运行售前 Agent 真实评测，请等待全部案例完成……", flush=True)
    report = await evaluation_service.run()
    summary = {
        "run_id": report.run_id,
        "suite_version": report.suite_version,
        "total_cases": report.total_cases,
        "passed_cases": report.passed_cases,
        "failed_cases": report.failed_cases,
        "pass_rate": report.pass_rate,
        "tool_selection_accuracy": report.tool_selection_accuracy,
        "average_duration_ms": report.average_duration_ms,
        "p50_duration_ms": report.p50_duration_ms,
        "p95_duration_ms": report.p95_duration_ms,
        "failure_summary": report.failure_summary,
        "failed_results": [
            {
                "id": result.id,
                "question": result.question,
                "expected_tools": result.expected_tools,
                "actual_tools": result.actual_tools,
                "failures": result.failures,
                "failure_types": result.failure_types,
                "answer": result.answer,
            }
            for result in report.results
            if not result.passed
        ],
    }
    print("EVALUATION_SUMMARY_START", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print("EVALUATION_SUMMARY_END", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
