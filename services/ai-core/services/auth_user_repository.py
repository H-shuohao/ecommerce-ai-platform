import sqlite3
from datetime import datetime, timezone

from app.core.jwt_auth import JwtUser
from app.schemas.auth import AuthUserResponse, LoginAuditResponse
from database import Database, database


class AuthUserRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: str,
    ) -> AuthUserResponse:
        normalized_username = username.strip()
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self.db.lock, self.db.connection:
                self.db.connection.execute(
                    """
                    INSERT INTO auth_users
                    (username, password_hash, role, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (normalized_username, password_hash, role, now, now),
                )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed" in str(error):
                raise ValueError("用户名已存在") from error
            raise
        return AuthUserResponse(
            username=normalized_username,
            role=role,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    def get_login_user(self, username: str) -> JwtUser | None:
        with self.db.lock:
            row = self.db.connection.execute(
                """
                SELECT username, password_hash, role
                FROM auth_users
                WHERE username = ? AND is_active = 1
                """,
                (username.strip(),),
            ).fetchone()
        if row is None:
            return None
        return JwtUser(
            username=row["username"],
            password_hash=row["password_hash"],
            role=row["role"],
        )

    def list_users(self, limit: int = 100) -> list[AuthUserResponse]:
        with self.db.lock:
            rows = self.db.connection.execute(
                """
                SELECT username, role, is_active, created_at, updated_at
                FROM auth_users ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            AuthUserResponse(
                username=row["username"],
                role=row["role"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def record_login(
        self,
        *,
        username: str,
        success: bool,
        reason: str | None,
        client_ip: str | None,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            self.db.connection.execute(
                """
                INSERT INTO login_audits
                (username, success, reason, client_ip, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username.strip(), int(success), reason, client_ip, created_at),
            )

    def list_login_audits(self, limit: int = 100) -> list[LoginAuditResponse]:
        with self.db.lock:
            rows = self.db.connection.execute(
                """
                SELECT id, username, success, reason, client_ip, created_at
                FROM login_audits ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            LoginAuditResponse(
                id=row["id"],
                username=row["username"],
                success=bool(row["success"]),
                reason=row["reason"],
                client_ip=row["client_ip"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


auth_user_repository = AuthUserRepository()
