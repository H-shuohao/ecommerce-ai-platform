from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.schemas.content_agents import ContentDraft, ContentGenerateResponse, ContentTone
from database import Database, database


class ContentDraftRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    def create(self, content: ContentGenerateResponse, tone: ContentTone) -> str:
        draft_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            self.db.connection.execute(
                """
                INSERT INTO content_drafts
                (id, product_id, platform, tone, title, body, hashtags_json,
                 source_facts_json, status, review_comment, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
                """,
                (
                    draft_id,
                    content.product_id,
                    content.platform,
                    tone,
                    content.title,
                    content.body,
                    json.dumps(content.hashtags, ensure_ascii=False),
                    json.dumps(content.source_facts, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return draft_id

    @staticmethod
    def _to_model(row) -> ContentDraft:
        return ContentDraft(
            draft_id=row["id"],
            product_id=row["product_id"],
            platform=row["platform"],
            tone=row["tone"],
            title=row["title"],
            body=row["body"],
            hashtags=json.loads(row["hashtags_json"]),
            source_facts=json.loads(row["source_facts_json"]),
            human_review_required=row["status"] != "approved",
            status=row["status"],
            review_comment=row["review_comment"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get(self, draft_id: str) -> ContentDraft | None:
        with self.db.lock:
            row = self.db.connection.execute(
                "SELECT * FROM content_drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
        return self._to_model(row) if row else None

    def list(self, status: str | None = None, limit: int = 20) -> list[ContentDraft]:
        with self.db.lock:
            if status:
                rows = self.db.connection.execute(
                    """
                    SELECT * FROM content_drafts
                    WHERE status = ? ORDER BY created_at DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = self.db.connection.execute(
                    "SELECT * FROM content_drafts ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._to_model(row) for row in rows]

    def review(self, draft_id: str, action: str, comment: str | None) -> ContentDraft | None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE content_drafts
                SET status = ?, review_comment = ?, updated_at = ?
                WHERE id = ?
                """,
                (action, comment, now, draft_id),
            )
        if cursor.rowcount == 0:
            return None
        return self.get(draft_id)

    def update(
        self,
        draft_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        hashtags: list[str] | None = None,
    ) -> ContentDraft | None:
        existing = self.get(draft_id)
        if existing is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            self.db.connection.execute(
                """
                UPDATE content_drafts
                SET title = ?, body = ?, hashtags_json = ?, status = 'pending',
                    review_comment = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    title if title is not None else existing.title,
                    body if body is not None else existing.body,
                    json.dumps(
                        hashtags if hashtags is not None else existing.hashtags,
                        ensure_ascii=False,
                    ),
                    now,
                    draft_id,
                ),
            )
        return self.get(draft_id)


content_draft_repository = ContentDraftRepository()
