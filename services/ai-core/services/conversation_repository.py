import uuid
from datetime import datetime, timezone

from app.schemas.memory import ConversationMessage, ConversationSession
from database import Database, database


class ConversationRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    def ensure_session(self, session_id: str | None = None) -> str:
        resolved_id = session_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            self.db.connection.execute(
                """
                INSERT OR IGNORE INTO conversation_sessions (id, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (resolved_id, now, now),
            )
        return resolved_id

    def append_exchange(self, session_id: str, question: str, answer: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            session = self.db.connection.execute(
                "SELECT id FROM conversation_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise KeyError("会话不存在")
            self.db.connection.executemany(
                """
                INSERT INTO conversation_messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (session_id, "user", question, now),
                    (session_id, "assistant", answer, now),
                ],
            )
            self.db.connection.execute(
                "UPDATE conversation_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )

    def get_recent_messages(self, session_id: str, limit: int = 6) -> list[dict[str, str]]:
        with self.db.lock:
            rows = self.db.connection.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content
                    FROM conversation_messages
                    WHERE session_id = ?
                    ORDER BY id DESC LIMIT ?
                ) ORDER BY id ASC
                """,
                (session_id, limit),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def get_session(self, session_id: str) -> ConversationSession | None:
        with self.db.lock:
            session = self.db.connection.execute(
                "SELECT * FROM conversation_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if session is None:
                return None
            rows = self.db.connection.execute(
                """
                SELECT role, content, created_at
                FROM conversation_messages WHERE session_id = ? ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
        return ConversationSession(
            id=session["id"],
            created_at=session["created_at"],
            updated_at=session["updated_at"],
            messages=[ConversationMessage(**dict(row)) for row in rows],
        )


conversation_repository = ConversationRepository()
