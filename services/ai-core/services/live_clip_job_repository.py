from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from app.schemas.live_clips import (
    LiveClipPipelineJob,
    LiveClipPipelineRequest,
    LiveClipPipelineStatus,
    TranscriptSegment,
)
from database import Database, database


class LiveClipJobRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _request_payload(request: LiveClipPipelineRequest) -> tuple[str, str]:
        payload = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return payload, fingerprint

    @staticmethod
    def _to_model(row) -> LiveClipPipelineJob:
        return LiveClipPipelineJob(
            id=row["id"],
            idempotency_key=row["idempotency_key"],
            product_id=row["product_id"],
            source_asset_id=row["source_asset_id"],
            transcript_segment_count=row["transcript_segment_count"],
            transcript_source=row["transcript_source"],
            max_clips=row["max_clips"],
            status=row["status"],
            stage=row["stage"],
            planned_asset_ids=json.loads(row["planned_asset_ids_json"]),
            output_asset_ids=json.loads(row["output_asset_ids_json"]),
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
        request: LiveClipPipelineRequest,
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> LiveClipPipelineJob:
        job_id = str(uuid.uuid4())
        now = self._now()
        request_json, request_fingerprint = self._request_payload(request)
        existing_row = None
        with self.db.lock, self.db.connection:
            statement = (
                """
                INSERT OR IGNORE INTO live_clip_pipeline_jobs
                (id, idempotency_key, request_fingerprint, product_id,
                 source_asset_id, transcript_json, transcript_segment_count,
                 transcript_source,
                 max_clips, status, stage, planned_asset_ids_json,
                 output_asset_ids_json, error, attempt_count, max_attempts,
                 created_at, updated_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'queued', '[]', '[]',
                        NULL, 0, ?, ?, ?, NULL, NULL)
                """
                if idempotency_key
                else """
                INSERT INTO live_clip_pipeline_jobs
                (id, idempotency_key, request_fingerprint, product_id,
                 source_asset_id, transcript_json, transcript_segment_count,
                 transcript_source,
                 max_clips, status, stage, planned_asset_ids_json,
                 output_asset_ids_json, error, attempt_count, max_attempts,
                 created_at, updated_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'queued', '[]', '[]',
                        NULL, 0, ?, ?, ?, NULL, NULL)
                """
            )
            cursor = self.db.connection.execute(
                statement,
                (
                    job_id,
                    idempotency_key,
                    request_fingerprint,
                    request.product_id,
                    request.source_asset_id,
                    request_json,
                    len(request.transcript),
                    "provided" if request.transcript else "asr",
                    request.max_clips,
                    max_attempts,
                    now,
                    now,
                ),
            )
            if idempotency_key and cursor.rowcount == 0:
                existing_row = self.db.connection.execute(
                    """
                    SELECT * FROM live_clip_pipeline_jobs
                    WHERE idempotency_key = ?
                    """,
                    (idempotency_key,),
                ).fetchone()

        if existing_row is not None:
            if existing_row["request_fingerprint"] != request_fingerprint:
                raise ValueError("该幂等键已经用于另一个直播切片请求")
            return self._to_model(existing_row)
        job = self.get(job_id)
        if job is None:
            raise RuntimeError("直播切片流水线任务创建失败")
        return job

    def get(self, job_id: str) -> LiveClipPipelineJob | None:
        with self.db.lock:
            row = self.db.connection.execute(
                "SELECT * FROM live_clip_pipeline_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._to_model(row) if row else None

    def load_request(self, job_id: str) -> LiveClipPipelineRequest | None:
        with self.db.lock:
            row = self.db.connection.execute(
                "SELECT transcript_json FROM live_clip_pipeline_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return LiveClipPipelineRequest.model_validate_json(row["transcript_json"])

    def save_transcript(
        self,
        job_id: str,
        transcript: list[TranscriptSegment],
    ) -> LiveClipPipelineJob | None:
        if not transcript:
            raise ValueError("ASR 转写不能为空")
        request = self.load_request(job_id)
        if request is None:
            return None
        updated_request = request.model_copy(update={"transcript": transcript})
        request_json = json.dumps(
            updated_request.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE live_clip_pipeline_jobs
                SET transcript_json = ?, transcript_segment_count = ?,
                    transcript_source = 'asr', stage = 'planning',
                    updated_at = ?
                WHERE id = ? AND status = 'running'
                  AND transcript_segment_count = 0
                """,
                (request_json, len(transcript), now, job_id),
            )
        return self.get(job_id) if cursor.rowcount else None

    def list(
        self,
        *,
        status: LiveClipPipelineStatus | None = None,
        limit: int = 20,
    ) -> list[LiveClipPipelineJob]:
        with self.db.lock:
            if status is None:
                rows = self.db.connection.execute(
                    """
                    SELECT * FROM live_clip_pipeline_jobs
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = self.db.connection.execute(
                    """
                    SELECT * FROM live_clip_pipeline_jobs
                    WHERE status = ? ORDER BY created_at DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        return [self._to_model(row) for row in rows]

    def mark_running(self, job_id: str) -> LiveClipPipelineJob | None:
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE live_clip_pipeline_jobs
                SET status = 'running', attempt_count = attempt_count + 1,
                    stage = CASE
                        WHEN transcript_segment_count = 0
                        THEN 'transcribing' ELSE 'planning'
                    END,
                    error = NULL, started_at = ?, finished_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'queued' AND attempt_count < max_attempts
                """,
                (now, now, job_id),
            )
        return self.get(job_id) if cursor.rowcount else None

    def save_plan(
        self,
        job_id: str,
        planned_asset_ids: list[str],
    ) -> LiveClipPipelineJob | None:
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE live_clip_pipeline_jobs
                SET planned_asset_ids_json = ?, stage = 'cutting', updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (json.dumps(planned_asset_ids), now, job_id),
            )
        return self.get(job_id) if cursor.rowcount else None

    def append_output(
        self,
        job_id: str,
        output_asset_id: str,
    ) -> LiveClipPipelineJob | None:
        now = self._now()
        with self.db.lock, self.db.connection:
            row = self.db.connection.execute(
                """
                SELECT output_asset_ids_json FROM live_clip_pipeline_jobs
                WHERE id = ? AND status = 'running'
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            output_ids = json.loads(row["output_asset_ids_json"])
            if output_asset_id not in output_ids:
                output_ids.append(output_asset_id)
            self.db.connection.execute(
                """
                UPDATE live_clip_pipeline_jobs
                SET output_asset_ids_json = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (json.dumps(output_ids), now, job_id),
            )
        return self.get(job_id)

    def mark_succeeded(self, job_id: str) -> LiveClipPipelineJob | None:
        return self._finish(job_id, "succeeded")

    def mark_failed(
        self,
        job_id: str,
        error: str,
    ) -> LiveClipPipelineJob | None:
        return self._finish(job_id, "failed", error=error[:1000])

    def _finish(
        self,
        job_id: str,
        status: Literal["succeeded", "failed"],
        *,
        error: str | None = None,
    ) -> LiveClipPipelineJob | None:
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE live_clip_pipeline_jobs
                SET status = ?, stage = ?, error = ?,
                    finished_at = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (
                    status,
                    "completed" if status == "succeeded" else "failed",
                    error,
                    now,
                    now,
                    job_id,
                ),
            )
        return self.get(job_id) if cursor.rowcount else None

    def queue_retry(self, job_id: str) -> LiveClipPipelineJob | None:
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE live_clip_pipeline_jobs
                SET status = 'queued', stage = 'queued',
                    error = NULL, updated_at = ?,
                    started_at = NULL, finished_at = NULL
                WHERE id = ? AND status = 'failed' AND attempt_count < max_attempts
                """,
                (now, job_id),
            )
        return self.get(job_id) if cursor.rowcount else None

    def requeue_interrupted(self) -> int:
        now = self._now()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE live_clip_pipeline_jobs
                SET status = 'queued', stage = 'queued',
                    error = '服务重启，任务已从最近进度重新排队',
                    updated_at = ?, started_at = NULL, finished_at = NULL
                WHERE status = 'running'
                """,
                (now,),
            )
        return cursor.rowcount


live_clip_job_repository = LiveClipJobRepository()
