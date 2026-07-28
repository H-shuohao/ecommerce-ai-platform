from fastapi import APIRouter, Header, HTTPException, Query, status

from app.schemas.live_clips import (
    LiveClipExecutionResponse,
    LiveClipPipelineJob,
    LiveClipPipelineRequest,
    LiveClipPipelineStatus,
    LiveClipPlanRequest,
    LiveClipPlanResponse,
)
from services.ffmpeg_service import (
    FFmpegProcessingError,
    FFmpegUnavailableError,
)
from services.live_clip_agent_service import live_clip_agent_service
from services.live_clip_execution_service import live_clip_execution_service
from services.live_clip_job_repository import live_clip_job_repository
from services.live_clip_job_service import live_clip_job_service
from services.media_storage_service import (
    AssetFileError,
    AssetFileTooLargeError,
)


router = APIRouter(prefix="/api/v1/agents/live-clips", tags=["直播切片 Agent"])


@router.post(
    "/pipelines",
    response_model=LiveClipPipelineJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="异步提交直播回放选段与物理切片流水线",
)
async def create_live_clip_pipeline(
    request: LiveClipPipelineRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="X-Idempotency-Key",
        min_length=1,
        max_length=100,
    ),
) -> LiveClipPipelineJob:
    try:
        return live_clip_job_service.submit(
            request,
            idempotency_key=idempotency_key,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=error.args[0]) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get(
    "/pipelines",
    response_model=list[LiveClipPipelineJob],
    summary="查询直播切片流水线任务列表",
)
async def list_live_clip_pipelines(
    job_status: LiveClipPipelineStatus | None = Query(
        default=None,
        alias="status",
    ),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[LiveClipPipelineJob]:
    return live_clip_job_repository.list(status=job_status, limit=limit)


@router.get(
    "/pipelines/{job_id}",
    response_model=LiveClipPipelineJob,
    summary="查询直播切片流水线任务状态与产物",
)
async def get_live_clip_pipeline(job_id: str) -> LiveClipPipelineJob:
    job = live_clip_job_repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="直播切片流水线任务不存在")
    return job


@router.post(
    "/pipelines/{job_id}/retry",
    response_model=LiveClipPipelineJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="从最近成功片段继续重试失败的直播切片任务",
)
async def retry_live_clip_pipeline(job_id: str) -> LiveClipPipelineJob:
    try:
        return live_clip_job_service.retry(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=error.args[0]) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/plan", response_model=LiveClipPlanResponse, summary="根据直播转写生成高光切片计划")
async def plan_live_clips(request: LiveClipPlanRequest) -> LiveClipPlanResponse:
    try:
        return await live_clip_agent_service.plan(request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=error.args[0]) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post(
    "/plans/{planned_asset_id}/execute",
    response_model=LiveClipExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="使用 FFmpeg 物理裁剪候选片段并登记到素材中心",
)
async def execute_live_clip(
    planned_asset_id: str,
) -> LiveClipExecutionResponse:
    try:
        return await live_clip_execution_service.execute(planned_asset_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=error.args[0]) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except AssetFileTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except AssetFileError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except FFmpegUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except FFmpegProcessingError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
