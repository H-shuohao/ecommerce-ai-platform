from fastapi import APIRouter, Header, HTTPException, Query, status

from app.schemas.content_agents import (
    ContentDraft,
    ContentDraftUpdate,
    ContentComplianceResult,
    ContentGenerateRequest,
    ContentGenerateResponse,
    ContentGenerationJob,
    ContentJobStatus,
    ContentReviewRequest,
)
from app.schemas.media_assets import MediaAssetCreate
from services.content_agent_service import content_agent_service
from services.content_compliance_service import content_compliance_service
from services.content_draft_repository import content_draft_repository
from services.content_job_repository import content_job_repository
from services.content_job_service import content_job_service
from services.media_asset_service import media_asset_service


router = APIRouter(prefix="/api/v1/agents/content", tags=["内容运营 Agent"])


@router.post(
    "/generate",
    response_model=ContentGenerateResponse,
    summary="根据商品事实生成平台营销文案",
)
async def generate_content(request: ContentGenerateRequest) -> ContentGenerateResponse:
    try:
        content = await content_agent_service.generate(
            product_id=request.product_id,
            platform=request.platform,
            tone=request.tone,
        )
        draft_id = content_draft_repository.create(content, request.tone)
        return content.model_copy(update={"draft_id": draft_id, "status": "pending"})
    except KeyError as error:
        detail = error.args[0] if error.args else "资源不存在"
        raise HTTPException(status_code=404, detail=str(detail)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post(
    "/jobs",
    response_model=ContentGenerationJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="异步提交内容生成任务",
)
async def create_content_generation_job(
    request: ContentGenerateRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="X-Idempotency-Key",
        min_length=1,
        max_length=100,
    ),
) -> ContentGenerationJob:
    return content_job_service.submit(
        product_id=request.product_id,
        platform=request.platform,
        tone=request.tone,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/jobs",
    response_model=list[ContentGenerationJob],
    summary="查询内容生成任务列表",
)
async def list_content_generation_jobs(
    job_status: ContentJobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ContentGenerationJob]:
    return content_job_repository.list(status=job_status, limit=limit)


@router.get(
    "/jobs/{job_id}",
    response_model=ContentGenerationJob,
    summary="查询内容生成任务状态",
)
async def get_content_generation_job(job_id: str) -> ContentGenerationJob:
    job = content_job_repository.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="内容生成任务不存在")
    return job


@router.post(
    "/jobs/{job_id}/retry",
    response_model=ContentGenerationJob,
    status_code=status.HTTP_202_ACCEPTED,
    summary="重试失败的内容生成任务",
)
async def retry_content_generation_job(job_id: str) -> ContentGenerationJob:
    try:
        return content_job_service.retry(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get(
    "/drafts",
    response_model=list[ContentDraft],
    summary="查询内容草稿",
)
async def list_content_drafts(
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ContentDraft]:
    return content_draft_repository.list(status=status, limit=limit)


@router.get(
    "/drafts/{draft_id}",
    response_model=ContentDraft,
    summary="查询内容草稿详情",
)
async def get_content_draft(draft_id: str) -> ContentDraft:
    draft = content_draft_repository.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="内容草稿不存在")
    return draft


@router.patch(
    "/drafts/{draft_id}",
    response_model=ContentDraft,
    summary="人工编辑内容草稿",
)
async def update_content_draft(
    draft_id: str,
    request: ContentDraftUpdate,
) -> ContentDraft:
    draft = content_draft_repository.update(
        draft_id,
        title=request.title,
        body=request.body,
        hashtags=request.hashtags,
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="内容草稿不存在")
    return draft


@router.get(
    "/drafts/{draft_id}/compliance",
    response_model=ContentComplianceResult,
    summary="检查内容草稿合规风险",
)
async def check_content_draft_compliance(draft_id: str) -> ContentComplianceResult:
    draft = content_draft_repository.get(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="内容草稿不存在")
    return content_compliance_service.check(
        draft_id,
        draft.title,
        draft.body,
    )


@router.post(
    "/drafts/{draft_id}/review",
    response_model=ContentDraft,
    summary="人工批准或驳回内容草稿",
)
async def review_content_draft(
    draft_id: str,
    request: ContentReviewRequest,
) -> ContentDraft:
    existing = content_draft_repository.get(draft_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="内容草稿不存在")
    if request.action == "approved":
        compliance = content_compliance_service.check(
            draft_id,
            existing.title,
            existing.body,
        )
        if not compliance.passed:
            terms = "、".join(issue.term for issue in compliance.issues)
            raise HTTPException(
                status_code=409,
                detail=f"草稿包含高风险表达，不能批准: {terms}",
            )
    draft = content_draft_repository.review(
        draft_id,
        request.action,
        request.comment,
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="内容草稿不存在")
    if request.action == "approved":
        media_asset_service.create(
            MediaAssetCreate(
                asset_type="text",
                title=draft.title,
                uri=f"content-draft://{draft_id}",
                product_id=draft.product_id,
                source="content-agent-approved",
                tags=[draft.platform, *draft.hashtags],
            )
        )
    return draft
