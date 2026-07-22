from app.schemas.media_assets import MediaAsset, MediaAssetCreate
from services.commerce_service import commerce_service
from services.media_asset_repository import MediaAssetRepository, media_asset_repository


class MediaAssetService:
    def __init__(self, repository: MediaAssetRepository = media_asset_repository) -> None:
        self.repository = repository

    def create(self, request: MediaAssetCreate) -> MediaAsset:
        if request.product_id and commerce_service.get_product(request.product_id) is None:
            raise KeyError(f"商品不存在: {request.product_id}")
        existing = self.repository.get_by_uri(request.uri)
        if existing is not None:
            return existing
        normalized = request.model_copy(
            update={"tags": list(dict.fromkeys(tag.strip() for tag in request.tags if tag.strip()))}
        )
        return self.repository.create(normalized)

    def get(self, asset_id: str) -> MediaAsset | None:
        return self.repository.get(asset_id)

    def list(self, **filters) -> list[MediaAsset]:
        return self.repository.list(**filters)


media_asset_service = MediaAssetService()
