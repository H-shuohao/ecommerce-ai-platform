import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.schemas.observability import (
    AgentRunDetail,
    AgentRunMetrics,
    AgentRunSummary,
    StoredToolCall,
    ToolUsageMetric,
)
from database import Database, database


class AgentRunRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    def record(
        self,
        *,
        question: str,
        status: str,
        duration_ms: int,
        answer: str | None = None,
        rag_used: bool = False,
        tool_calls: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        calls = tool_calls or []

        with self.db.lock, self.db.connection:
            self.db.connection.execute(
                """
                INSERT INTO agent_runs
                (id, agent_name, question, answer, status, rag_used, duration_ms, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "presales",
                    question,
                    answer,
                    status,
                    int(rag_used),
                    duration_ms,
                    error,
                    created_at,
                ),
            )
            for sequence, call in enumerate(calls, start=1):
                self.db.connection.execute(
                    """
                    INSERT INTO tool_calls
                    (run_id, sequence, tool_name, arguments_json, result_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        sequence,
                        call["tool"],
                        json.dumps(call["arguments"], ensure_ascii=False),
                        json.dumps(call["result"], ensure_ascii=False),
                    ),
                )
        return run_id

    def list_runs(self, limit: int = 20) -> list[AgentRunSummary]:
        with self.db.lock:
            rows = self.db.connection.execute(
                """
                SELECT id, agent_name, question, status, rag_used, duration_ms, created_at
                FROM agent_runs ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            AgentRunSummary(
                id=row["id"],
                agent_name=row["agent_name"],
                question=row["question"],
                status=row["status"],
                rag_used=bool(row["rag_used"]),
                duration_ms=row["duration_ms"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_run(self, run_id: str) -> AgentRunDetail | None:
        with self.db.lock:
            run = self.db.connection.execute(
                "SELECT * FROM agent_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                return None
            rows = self.db.connection.execute(
                "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()

        calls = [
            StoredToolCall(
                sequence=row["sequence"],
                tool=row["tool_name"],
                arguments=json.loads(row["arguments_json"]),
                result=json.loads(row["result_json"]),
            )
            for row in rows
        ]
        return AgentRunDetail(
            id=run["id"],
            agent_name=run["agent_name"],
            question=run["question"],
            answer=run["answer"],
            status=run["status"],
            rag_used=bool(run["rag_used"]),
            duration_ms=run["duration_ms"],
            error=run["error"],
            created_at=run["created_at"],
            tool_calls=calls,
        )

    def get_metrics(self) -> AgentRunMetrics:
        with self.db.lock:
            run_totals = self.db.connection.execute(
                """
                SELECT
                    COUNT(*) AS total_runs,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_runs,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_runs,
                    COALESCE(AVG(duration_ms), 0) AS average_duration_ms,
                    SUM(CASE WHEN rag_used = 1 THEN 1 ELSE 0 END) AS rag_used_runs
                FROM agent_runs
                """
            ).fetchone()
            tool_rows = self.db.connection.execute(
                """
                SELECT tool_name, COUNT(*) AS call_count
                FROM tool_calls
                GROUP BY tool_name
                ORDER BY call_count DESC, tool_name ASC
                """
            ).fetchall()

        total_runs = int(run_totals["total_runs"] or 0)
        success_runs = int(run_totals["success_runs"] or 0)
        failed_runs = int(run_totals["failed_runs"] or 0)
        rag_used_runs = int(run_totals["rag_used_runs"] or 0)
        tool_usage = [
            ToolUsageMetric(tool=row["tool_name"], call_count=row["call_count"])
            for row in tool_rows
        ]
        return AgentRunMetrics(
            total_runs=total_runs,
            success_runs=success_runs,
            failed_runs=failed_runs,
            success_rate=round(success_runs / total_runs * 100, 2) if total_runs else 0.0,
            average_duration_ms=round(float(run_totals["average_duration_ms"]), 2),
            rag_used_runs=rag_used_runs,
            rag_usage_rate=round(rag_used_runs / total_runs * 100, 2) if total_runs else 0.0,
            total_tool_calls=sum(item.call_count for item in tool_usage),
            tool_usage=tool_usage,
        )


agent_run_repository = AgentRunRepository()
