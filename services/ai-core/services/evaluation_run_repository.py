import json
import uuid
from datetime import datetime, timezone

from app.schemas.evaluations import (
    EvaluationCaseResult,
    EvaluationReport,
    EvaluationRunSummary,
    StoredEvaluationReport,
)
from database import Database, database


class EvaluationRunRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    def record(self, report: EvaluationReport) -> str:
        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            self.db.connection.execute(
                """
                INSERT INTO evaluation_runs
                (id, suite_name, suite_version, total_cases, passed_cases,
                 failed_cases, pass_rate, tool_selection_accuracy,
                 average_duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    report.suite_name,
                    report.suite_version,
                    report.total_cases,
                    report.passed_cases,
                    report.failed_cases,
                    report.pass_rate,
                    report.tool_selection_accuracy,
                    report.average_duration_ms,
                    created_at,
                ),
            )
            for result in report.results:
                self.db.connection.execute(
                    """
                    INSERT INTO evaluation_case_results
                    (run_id, case_id, question, passed, expected_tools_json,
                     actual_tools_json, answer, duration_ms, failures_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        result.id,
                        result.question,
                        int(result.passed),
                        json.dumps(result.expected_tools, ensure_ascii=False),
                        json.dumps(result.actual_tools, ensure_ascii=False),
                        result.answer,
                        result.duration_ms,
                        json.dumps(result.failures, ensure_ascii=False),
                    ),
                )
        return run_id

    @staticmethod
    def _summary(row) -> EvaluationRunSummary:
        return EvaluationRunSummary(
            run_id=row["id"],
            suite_name=row["suite_name"],
            suite_version=row["suite_version"],
            total_cases=row["total_cases"],
            passed_cases=row["passed_cases"],
            failed_cases=row["failed_cases"],
            pass_rate=row["pass_rate"],
            tool_selection_accuracy=row["tool_selection_accuracy"],
            average_duration_ms=row["average_duration_ms"],
            created_at=row["created_at"],
        )

    def list_runs(self, limit: int = 20) -> list[EvaluationRunSummary]:
        with self.db.lock:
            rows = self.db.connection.execute(
                "SELECT * FROM evaluation_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._summary(row) for row in rows]

    def get_run(self, run_id: str) -> StoredEvaluationReport | None:
        with self.db.lock:
            run = self.db.connection.execute(
                "SELECT * FROM evaluation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                return None
            rows = self.db.connection.execute(
                "SELECT * FROM evaluation_case_results WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        summary = self._summary(run)
        results = [
            EvaluationCaseResult(
                id=row["case_id"],
                question=row["question"],
                passed=bool(row["passed"]),
                expected_tools=json.loads(row["expected_tools_json"]),
                actual_tools=json.loads(row["actual_tools_json"]),
                answer=row["answer"],
                duration_ms=row["duration_ms"],
                failures=json.loads(row["failures_json"]),
            )
            for row in rows
        ]
        return StoredEvaluationReport(**summary.model_dump(), results=results)


evaluation_run_repository = EvaluationRunRepository()
