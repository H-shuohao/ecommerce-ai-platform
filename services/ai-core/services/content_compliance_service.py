from app.schemas.content_agents import ComplianceIssue, ContentComplianceResult


HIGH_RISK_RULES = {
    "absolute_claim": ["百分百有效", "全网第一", "绝对安全", "永久有效", "顶级品质"],
    "medical_claim": ["治疗", "治愈", "根治", "药效", "替代药物"],
}
MEDIUM_RISK_RULES = {
    "unverified_promotion": ["销量第一", "限时优惠", "最低价", "库存仅剩"],
}

MESSAGES = {
    "absolute_claim": "包含绝对化宣传表达",
    "medical_claim": "普通商品文案包含医疗功效表达",
    "unverified_promotion": "包含未由商品事实支持的促销或销量表达",
}


class ContentComplianceService:
    def check(self, draft_id: str, title: str, body: str) -> ContentComplianceResult:
        text = f"{title}\n{body}"
        issues: list[ComplianceIssue] = []
        for category, terms in HIGH_RISK_RULES.items():
            for term in terms:
                if term in text:
                    issues.append(
                        ComplianceIssue(
                            category=category,
                            term=term,
                            message=MESSAGES[category],
                            severity="high",
                        )
                    )
        for category, terms in MEDIUM_RISK_RULES.items():
            for term in terms:
                if term in text:
                    issues.append(
                        ComplianceIssue(
                            category=category,
                            term=term,
                            message=MESSAGES[category],
                            severity="medium",
                        )
                    )

        if any(issue.severity == "high" for issue in issues):
            risk_level = "high"
        elif issues:
            risk_level = "medium"
        else:
            risk_level = "low"
        return ContentComplianceResult(
            draft_id=draft_id,
            passed=risk_level != "high",
            risk_level=risk_level,
            issues=issues,
        )


content_compliance_service = ContentComplianceService()
