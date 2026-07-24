from fastapi import APIRouter, HTTPException

from app.schemas.data_platform import (
    CommerceStagingRequest,
    DataCatalog,
    DataQualityReport,
    DataRelease,
    StagingValidationResponse,
)
from services.data_publication_service import data_publication_service
from services.data_release_repository import data_release_repository
from services.data_platform_service import data_platform_service
from services.commerce_service import commerce_service


router = APIRouter(prefix="/api/v1/data-platform", tags=["AI 数据中台"])


@router.get(
    "/cache/commerce",
    summary="查看商品查询缓存指标",
)
async def get_commerce_cache_stats() -> dict:
    stats = commerce_service.get_product_cache_stats()
    return {
        "size": stats.size,
        "max_entries": stats.max_entries,
        "ttl_seconds": stats.ttl_seconds,
        "hits": stats.hits,
        "misses": stats.misses,
        "evictions": stats.evictions,
        "hit_rate": stats.hit_rate,
    }


@router.delete(
    "/cache/commerce",
    summary="清空商品查询缓存",
)
async def clear_commerce_cache() -> dict:
    cleared_entries = commerce_service.clear_product_cache()
    return {
        "cleared_entries": cleared_entries,
        "status": "cleared",
    }


@router.get(
    "/catalog",
    response_model=DataCatalog,
    summary="查询统一数据资产目录",
)
async def get_data_catalog() -> DataCatalog:
    return data_platform_service.get_catalog()


@router.get(
    "/quality/commerce",
    response_model=DataQualityReport,
    summary="检查电商数据质量",
)
async def check_commerce_data_quality() -> DataQualityReport:
    return data_platform_service.check_commerce_quality()


@router.post(
    "/staging/commerce/validate",
    response_model=StagingValidationResponse,
    summary="预检候选电商数据且不影响正式版本",
)
async def validate_staging_commerce_data(
    request: CommerceStagingRequest,
) -> StagingValidationResponse:
    try:
        report = data_platform_service.preview_commerce_quality(request.data)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return StagingValidationResponse(
        ready_to_publish=report.failed_checks == 0,
        persisted=False,
        quality_report=report,
    )


@router.post(
    "/releases/commerce",
    response_model=DataRelease,
    summary="质检并发布电商数据版本",
)
async def publish_commerce_data() -> DataRelease:
    return data_publication_service.publish_commerce()


@router.get(
    "/releases/commerce",
    response_model=list[DataRelease],
    summary="查询电商数据发布历史",
)
async def list_commerce_data_releases() -> list[DataRelease]:
    return data_release_repository.list(dataset="commerce")


@router.post(
    "/releases/commerce/{release_id}/activate",
    response_model=DataRelease,
    summary="激活或回滚到已发布电商数据版本",
)
async def activate_commerce_data_release(release_id: str) -> DataRelease:
    try:
        return data_publication_service.activate_commerce_release(release_id)
    except KeyError as error:
        detail = error.args[0] if error.args else "数据版本不存在"
        raise HTTPException(status_code=404, detail=str(detail)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
