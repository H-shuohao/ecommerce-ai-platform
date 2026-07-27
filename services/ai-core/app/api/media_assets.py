from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.schemas.media_assets import (
    AssetType,
    MediaAsset,
    MediaAssetCreate,
    MediaAssetListResponse,
)
from services.media_asset_service import media_asset_service
from services.media_storage_service import (
    AssetFileError,
    AssetFileTooLargeError,
    media_storage_service,
)


router = APIRouter(prefix="/api/v1/assets", tags=["多模态素材中心"])


@router.post("", response_model=MediaAsset, status_code=201, summary="登记素材元数据")
async def create_media_asset(request: MediaAssetCreate) -> MediaAsset:
    try:
        return media_asset_service.create(request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=error.args[0]) from error


@router.post(
    "/upload",
    response_model=MediaAsset,
    status_code=status.HTTP_201_CREATED,
    summary="上传并登记图片、视频或文本素材",
)
async def upload_media_asset(
    response: Response,
    file: Annotated[UploadFile, File(description="图片、视频或文本文件")],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    product_id: Annotated[str | None, Form(max_length=50)] = None,
    source: Annotated[str, Form(min_length=1, max_length=100)] = "manual-upload",
    tags: Annotated[str, Form(description="多个标签用英文逗号分隔")] = "",
) -> MediaAsset:
    try:
        media_asset_service.validate_product(product_id)
        stored = await media_storage_service.store(file)
        asset = media_asset_service.create(
            MediaAssetCreate(
                asset_type=stored.asset_type,
                title=title,
                uri=stored.uri,
                product_id=product_id,
                source=source,
                tags=[item.strip() for item in tags.split(",") if item.strip()],
                storage_provider="local",
                original_filename=stored.original_filename,
                content_type=stored.content_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
            )
        )
        response.headers["X-Asset-Deduplicated"] = str(
            stored.deduplicated
        ).lower()
        return asset
    except KeyError as error:
        raise HTTPException(status_code=404, detail=error.args[0]) from error
    except AssetFileTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except AssetFileError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


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


@router.get(
    "/{asset_id}/content",
    response_class=FileResponse,
    summary="下载本地素材文件",
)
async def download_media_asset(asset_id: str) -> FileResponse:
    asset = media_asset_service.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    try:
        path = media_storage_service.resolve(asset.uri)
    except AssetFileError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not path.is_file():
        raise HTTPException(status_code=404, detail="素材文件不存在")
    return FileResponse(
        path,
        media_type=asset.content_type,
        filename=asset.original_filename or path.name,
    )


@router.get("/{asset_id}", response_model=MediaAsset, summary="查询素材详情")
async def get_media_asset(asset_id: str) -> MediaAsset:
    asset = media_asset_service.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return asset
