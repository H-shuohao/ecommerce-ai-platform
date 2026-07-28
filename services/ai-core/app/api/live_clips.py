from fastapi import APIRouter, HTTPException, status

from app.schemas.live_clips import (
    LiveClipExecutionResponse,
    LiveClipPlanRequest,
    LiveClipPlanResponse,
)
from services.ffmpeg_service import (
    FFmpegProcessingError,
    FFmpegUnavailableError,
)
from services.live_clip_agent_service import live_clip_agent_service
from services.live_clip_execution_service import live_clip_execution_service
from services.media_storage_service import (
    AssetFileError,
    AssetFileTooLargeError,
)


router = APIRouter(prefix="/api/v1/agents/live-clips", tags=["直播切片 Agent"])


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
