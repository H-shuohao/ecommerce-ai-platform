from services.media_asset_service import media_asset_service


def search_media_assets(
    product_id: str | None = None,
    asset_type: str | None = None,
    tag: str | None = None,
) -> dict:
    if asset_type not in {None, "image", "video", "text"}:
        raise ValueError("asset_type 只能是 image、video 或 text")
    items = media_asset_service.list(
        product_id=product_id,
        asset_type=asset_type,
        tag=tag,
        limit=20,
    )
    return {
        "items": [item.model_dump() for item in items],
        "total": len(items),
    }
