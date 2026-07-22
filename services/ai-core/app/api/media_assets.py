from fastapi import APIRouter, HTTPException, Query

from app.schemas.media_assets import (
    AssetType,
    MediaAsset,
    MediaAssetCreate,
    MediaAssetListResponse,
)
from services.media_asset_service import media_asset_service


router = APIRouter(prefix="/api/v1/assets", tags=["多模态素材中心"])


@router.post("", response_model=MediaAsset, status_code=201, summary="登记素材元数据")
async def create_media_asset(request: MediaAssetCreate) -> MediaAsset:
    try:
        return media_asset_service.create(request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=error.args[0]) from error


@router.get("", response_model=MediaAssetListResponse, summary="检索可用素材")
async def list_media_assets(
    product_id: str | None = None,
    asset_type: AssetType | None = None,
    tag: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> MediaAssetListResponse:
    items = media_asset_service.list(
        product_id=product_id,
        asset_type=asset_type,
        tag=tag,
        limit=limit,
    )
    return MediaAssetListResponse(items=items, total=len(items))


@router.get("/{asset_id}", response_model=MediaAsset, summary="查询素材详情")
async def get_media_asset(asset_id: str) -> MediaAsset:
    asset = media_asset_service.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return asset
