from app.schemas.evaluations import EvaluationComparison, StoredEvaluationReport
from services.evaluation_run_repository import EvaluationRunRepository, evaluation_run_repository


class EvaluationComparisonService:
    def __init__(
        self,
        repository: EvaluationRunRepository = evaluation_run_repository,
    ) -> None:
        self.repository = repository

    def compare(self, baseline_run_id: str, candidate_run_id: str) -> EvaluationComparison:
        baseline = self.repository.get_run(baseline_run_id)
        candidate = self.repository.get_run(candidate_run_id)
        if baseline is None:
            raise KeyError("基线评测记录不存在")
        if candidate is None:
            raise KeyError("候选评测记录不存在")
        self._validate_compatible(baseline, candidate)

        baseline_cases = {result.id: result for result in baseline.results}
        candidate_cases = {result.id: result for result in candidate.results}
        if set(baseline_cases) != set(candidate_cases):
            raise ValueError("两次评测的案例集合不同，不能直接比较")

        improved: list[str] = []
        regressed: list[str] = []
        unchanged: list[str] = []
        for case_id in baseline_cases:
            before = baseline_cases[case_id].passed
            after = candidate_cases[case_id].passed
            if not before and after:
                improved.append(case_id)
            elif before and not after:
                regressed.append(case_id)
            else:
                unchanged.append(case_id)

        pass_rate_delta = round(candidate.pass_rate - baseline.pass_rate, 2)
        accuracy_delta = round(
            candidate.tool_selection_accuracy - baseline.tool_selection_accuracy,
            2,
        )
        duration_delta = round(
            candidate.average_duration_ms - baseline.average_duration_ms,
            2,
        )
        if regressed:
            recommendation = "存在案例退化，建议先定位原因，不直接替换基线版本"
        elif improved:
            recommendation = "存在案例提升且没有退化，可以继续扩大评测集验证"
        elif duration_delta < 0:
            recommendation = "正确率保持不变且平均耗时下降，可以考虑采用候选版本"
        else:
            recommendation = "核心正确率没有变化，需要结合成本和更多案例判断"

        return EvaluationComparison(
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
            suite_name=baseline.suite_name,
            suite_version=baseline.suite_version,
            pass_rate_delta=pass_rate_delta,
            tool_selection_accuracy_delta=accuracy_delta,
            average_duration_ms_delta=duration_delta,
            improved_cases=improved,
            regressed_cases=regressed,
            unchanged_cases=unchanged,
            recommendation=recommendation,
        )

    @staticmethod
    def _validate_compatible(
        baseline: StoredEvaluationReport,
        candidate: StoredEvaluationReport,
    ) -> None:
        if baseline.suite_name != candidate.suite_name:
            raise ValueError("两次评测属于不同套件，不能直接比较")
        if baseline.suite_version != candidate.suite_version:
            raise ValueError("两次评测集版本不同，不能直接比较")


evaluation_comparison_service = EvaluationComparisonService()
