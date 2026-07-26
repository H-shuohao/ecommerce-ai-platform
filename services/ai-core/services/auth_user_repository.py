import sqlite3
from datetime import datetime, timezone

from app.core.jwt_auth import JwtUser, verify_password
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
                SELECT username, password_hash, role, token_version
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
            token_version=row["token_version"],
        )

    def get_token_state(self, username: str) -> tuple[bool, int] | None:
        with self.db.lock:
            row = self.db.connection.execute(
                """
                SELECT is_active, token_version
                FROM auth_users WHERE username = ?
                """,
                (username.strip(),),
            ).fetchone()
        if row is None:
            return None
        return bool(row["is_active"]), int(row["token_version"])

    def change_password(
        self,
        *,
        username: str,
        current_password: str,
        new_password_hash: str,
    ) -> bool:
        user = self.get_login_user(username)
        if user is None:
            return False
        if not verify_password(current_password, user.password_hash):
            return False
        now = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            self.db.connection.execute(
                """
                UPDATE auth_users
                SET password_hash = ?, token_version = token_version + 1,
                    updated_at = ?
                WHERE username = ? AND is_active = 1
                """,
                (new_password_hash, now, username.strip()),
            )
        return True

    def set_active(self, *, username: str, is_active: bool) -> AuthUserResponse | None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            cursor = self.db.connection.execute(
                """
                UPDATE auth_users
                SET is_active = ?, token_version = token_version + 1,
                    updated_at = ?
                WHERE username = ?
                """,
                (int(is_active), now, username.strip()),
            )
            if cursor.rowcount == 0:
                return None
            row = self.db.connection.execute(
                """
                SELECT username, role, is_active, created_at, updated_at
                FROM auth_users WHERE username = ?
                """,
                (username.strip(),),
            ).fetchone()
        return AuthUserResponse(
            username=row["username"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
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
