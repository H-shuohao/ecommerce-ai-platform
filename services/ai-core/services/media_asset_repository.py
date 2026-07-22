import json
import uuid
from datetime import datetime, timezone

from app.schemas.media_assets import MediaAsset, MediaAssetCreate
from database import Database, database


class MediaAssetRepository:
    def __init__(self, db: Database = database) -> None:
        self.db = db

    @staticmethod
    def _to_model(row) -> MediaAsset:
        return MediaAsset(
            id=row["id"],
            asset_type=row["asset_type"],
            title=row["title"],
            uri=row["uri"],
            product_id=row["product_id"],
            source=row["source"],
            tags=json.loads(row["tags_json"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(self, request: MediaAssetCreate) -> MediaAsset:
        asset_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.db.lock, self.db.connection:
            self.db.connection.execute(
                """
                INSERT INTO media_assets
                (id, asset_type, title, uri, product_id, source, tags_json,
                 status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    asset_id,
                    request.asset_type,
                    request.title,
                    request.uri,
                    request.product_id,
                    request.source,
                    json.dumps(request.tags, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get(asset_id)

    def get(self, asset_id: str) -> MediaAsset | None:
        with self.db.lock:
            row = self.db.connection.execute(
                "SELECT * FROM media_assets WHERE id = ?",
                (asset_id,),
            ).fetchone()
        return self._to_model(row) if row else None

    def get_by_uri(self, uri: str) -> MediaAsset | None:
        with self.db.lock:
            row = self.db.connection.execute(
                "SELECT * FROM media_assets WHERE uri = ? ORDER BY created_at DESC LIMIT 1",
                (uri,),
            ).fetchone()
        return self._to_model(row) if row else None

    def list(
        self,
        *,
        product_id: str | None = None,
        asset_type: str | None = None,
        tag: str | None = None,
        limit: int = 20,
    ) -> list[MediaAsset]:
        conditions = ["status = 'active'"]
        parameters: list[object] = []
        if product_id:
            conditions.append("product_id = ?")
            parameters.append(product_id)
        if asset_type:
            conditions.append("asset_type = ?")
            parameters.append(asset_type)
        query = f"SELECT * FROM media_assets WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)
        with self.db.lock:
            rows = self.db.connection.execute(query, parameters).fetchall()
        assets = [self._to_model(row) for row in rows]
        if tag:
            normalized = tag.casefold()
            assets = [
                asset for asset in assets
                if any(item.casefold() == normalized for item in asset.tags)
            ]
        return assets


media_asset_repository = MediaAssetRepository()
