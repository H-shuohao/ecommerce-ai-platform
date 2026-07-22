from fastapi import APIRouter, HTTPException, Query

from app.schemas.evaluations import (
    EvaluationCase,
    EvaluationComparison,
    EvaluationReport,
    EvaluationRunSummary,
    StoredEvaluationReport,
)
from services.evaluation_run_repository import evaluation_run_repository
from services.evaluation_comparison_service import evaluation_comparison_service
from services.evaluation_service import evaluation_service


router = APIRouter(prefix="/api/v1/evaluations", tags=["AI 评测"])


@router.get(
    "/presales/cases",
    response_model=list[EvaluationCase],
    summary="查看售前 Agent 评测用例",
)
async def list_presales_evaluation_cases() -> list[EvaluationCase]:
    return evaluation_service.list_cases()


@router.post(
    "/presales/run",
    response_model=EvaluationReport,
    summary="运行售前 Agent 自动评测",
)
async def run_presales_evaluation() -> EvaluationReport:
    return await evaluation_service.run()


@router.get(
    "/presales/runs",
    response_model=list[EvaluationRunSummary],
    summary="查询售前 Agent 评测历史",
)
async def list_presales_evaluation_runs(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[EvaluationRunSummary]:
    return evaluation_run_repository.list_runs(limit=limit)


@router.get(
    "/presales/runs/{run_id}",
    response_model=StoredEvaluationReport,
    summary="查询一次售前 Agent 评测详情",
)
async def get_presales_evaluation_run(run_id: str) -> StoredEvaluationReport:
    report = evaluation_run_repository.get_run(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    return report


@router.get(
    "/presales/compare",
    response_model=EvaluationComparison,
    summary="对比两次售前 Agent 评测",
)
async def compare_presales_evaluations(
    baseline_run_id: str = Query(min_length=1),
    candidate_run_id: str = Query(min_length=1),
) -> EvaluationComparison:
    try:
        return evaluation_comparison_service.compare(
            baseline_run_id,
            candidate_run_id,
        )
    except KeyError as error:
        detail = error.args[0] if error.args else "评测记录不存在"
        raise HTTPException(status_code=404, detail=str(detail)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
