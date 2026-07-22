from fastapi import APIRouter, HTTPException

from app.schemas.live_clips import LiveClipPlanRequest, LiveClipPlanResponse
from services.live_clip_agent_service import live_clip_agent_service


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
