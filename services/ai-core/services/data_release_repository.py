import json
import uuid
from datetime import datetime, timezone

from app.schemas.data_platform import DataRelease
from database import Database, database


class DataReleaseRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    def record(
        self,
        *,
        dataset: str,
        version_hash: str,
        quality_score: float,
        status: str,
        snapshot: dict,
    ) -> DataRelease:
        release_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        is_active = status == "published"
        with self.db.lock, self.db.connection:
            if is_active:
                self.db.connection.execute(
                    "UPDATE data_releases SET is_active = 0 WHERE dataset = ?",
                    (dataset,),
                )
            self.db.connection.execute(
                """
                INSERT INTO data_releases
                (id, dataset, version_hash, quality_score, status, is_active,
                 snapshot_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    release_id,
                    dataset,
                    version_hash,
                    quality_score,
                    status,
                    int(is_active),
                    json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
        return DataRelease(
            id=release_id,
            dataset=dataset,
            version_hash=version_hash,
            quality_score=quality_score,
            status=status,
            is_active=is_active,
            created_at=created_at,
        )

    def list(self, dataset: str = "commerce", limit: int = 20) -> list[DataRelease]:
        with self.db.lock:
            rows = self.db.connection.execute(
                """
                SELECT id, dataset, version_hash, quality_score, status,
                       is_active, created_at
                FROM data_releases WHERE dataset = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (dataset, limit),
            ).fetchall()
        return [
            DataRelease(
                id=row["id"],
                dataset=row["dataset"],
                version_hash=row["version_hash"],
                quality_score=row["quality_score"],
                status=row["status"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def activate(self, release_id: str) -> tuple[DataRelease, dict] | None:
        with self.db.lock, self.db.connection:
            row = self.db.connection.execute(
                "SELECT * FROM data_releases WHERE id = ?",
                (release_id,),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "published":
                raise ValueError("被阻断的数据版本不能激活")
            self.db.connection.execute(
                "UPDATE data_releases SET is_active = 0 WHERE dataset = ?",
                (row["dataset"],),
            )
            self.db.connection.execute(
                "UPDATE data_releases SET is_active = 1 WHERE id = ?",
                (release_id,),
            )
        release = DataRelease(
            id=row["id"],
            dataset=row["dataset"],
            version_hash=row["version_hash"],
            quality_score=row["quality_score"],
            status=row["status"],
            is_active=True,
            created_at=row["created_at"],
        )
        return release, json.loads(row["snapshot_json"])


data_release_repository = DataReleaseRepository()
