from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from app.schemas.content_agents import (
    ContentGenerationJob,
    ContentJobStatus,
    ContentPlatform,
    ContentTone,
)
from database import Database, database


class ContentJobRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _to_model(row) -> ContentGenerationJob:
        return ContentGenerationJob(
            id=row["id"],
            idempotency_key=row["idempotency_key"],
            product_id=row["product_id"],
            platform=row["platform"],
            tone=row["tone"],
            status=row["status"],
            draft_id=row["draft_id"],
            error=row["error"],
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    def create(
        self,
        *,
        product_id: str,
        platform: ContentPlatform,
        tone: ContentTone,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> ContentGenerationJob:
        job_id = str(uuid.uuid4())
        now = self._now()
        existing_row = None
        with self.db.lock, self.db.connection:
            statement = (
                """
                INSERT OR IGNORE INTO content_generation_jobs
                (id, idempotency_key, product_id, platform, tone, status,
                 draft_id, error, attempt_count, max_attempts,
                 created_at, updated_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, 'queued', NULL, NULL, 0, ?, ?, ?, NULL, NULL)
                """
                if idempotency_key
                else """
                INSERT INTO content_generation_jobs
                (id, idempotency_key, product_id, platform, tone, status,
                 draft_id, error, attempt_count, max_attempts,
                 created_at, updated_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, 'queued', NULL, NULL, 0, ?, ?, ?, NULL, NULL)
                """
            )
            cursor = self.db.connection.execute(
                statement,
                (
                    job_id,
                    idempotency_key,
                    product_id,
                    platform,
                    tone,
                    max_attempts,
                    now,
                    now,
                ),
            )
            if idempotency_key and cursor.rowcount == 0:
                existing_row = self.db.connection.execute(
                    """
                    SELECT * FROM content_generation_jobs
                    WHERE idempotency_key = ?
                    """,
                    (idempotency_key,),
                ).fetchone()

        if existing_row is not None:
            return self._to_model(existing_row)

        job = self.get(job_id)
        if job is None:
            raise RuntimeError("内容生成任务创建失败")
        return job

    def get(self, job_id: str) -> ContentGenerationJob | None:
        with self.db.lock:
            row = self.db.connection.execute(
                "SELECT * FROM content_generation_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._to_model(row) if row else None

    def get_by_idempotency_key(self, key: str) -> ContentGenerationJob | None:
        with self.db.lock:
            row = self.db.connection.execute(
                "SELECT * FROM content_generation_jobs WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
        return self._to_model(row) if row else None

    def list(
        self,
        *,
        status: ContentJobStatus | None = None,
        limit: int = 20,
    ) -> list[ContentGenerationJob]:
        with self.db.lock:
            if status is None:
                rows = self.db.connection.execute(
                    """
                    SELECT * FROM content_generation_jobs
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = self.db.connection.execute(
                    """
                    SELECT * FROM content_generation_jobs
                    WHERE status = ? ORDER BY created_at DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        return [self._to_model(row) for row in rows]

    def mark_running(self, job_id: str) -> ContentGenerationJob | None:
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE content_generation_jobs
                SET status = 'running', attempt_count = attempt_count + 1,
                    error = NULL, started_at = ?, finished_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'queued' AND attempt_count < max_attempts
                """,
                (now, now, job_id),
            )
        return self.get(job_id) if cursor.rowcount else None

    def mark_succeeded(
        self,
        job_id: str,
        draft_id: str,
    ) -> ContentGenerationJob | None:
        return self._finish(job_id, "succeeded", draft_id=draft_id)

    def mark_failed(self, job_id: str, error: str) -> ContentGenerationJob | None:
        return self._finish(job_id, "failed", error=error[:1000])

    def _finish(
        self,
        job_id: str,
        status: Literal["succeeded", "failed"],
        *,
        draft_id: str | None = None,
        error: str | None = None,
    ) -> ContentGenerationJob | None:
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE content_generation_jobs
                SET status = ?, draft_id = ?, error = ?,
                    finished_at = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (status, draft_id, error, now, now, job_id),
            )
        return self.get(job_id) if cursor.rowcount else None

    def queue_retry(self, job_id: str) -> ContentGenerationJob | None:
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE content_generation_jobs
                SET status = 'queued', error = NULL, updated_at = ?,
                    started_at = NULL, finished_at = NULL
                WHERE id = ? AND status = 'failed' AND attempt_count < max_attempts
                """,
                (now, job_id),
            )
        return self.get(job_id) if cursor.rowcount else None

    def requeue_interrupted(self) -> int:
        """Move tasks interrupted by a process restart back to the queue."""
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE content_generation_jobs
                SET status = 'queued', error = '服务重启，任务已重新排队',
                    updated_at = ?, started_at = NULL, finished_at = NULL
                WHERE status = 'running'
                """,
                (now,),
            )
        return cursor.rowcount


content_job_repository = ContentJobRepository()
