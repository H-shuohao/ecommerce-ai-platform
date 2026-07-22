import unittest

from services.content_compliance_service import ContentComplianceService


class ContentComplianceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ContentComplianceService()

    def test_safe_content_passes(self) -> None:
        result = self.service.check(
            "draft-safe",
            "清爽通勤防晒",
            "质地轻薄不黏腻，适合油性和混合性肤质。",
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.risk_level, "low")
        self.assertEqual(result.issues, [])

    def test_medical_claim_is_high_risk(self) -> None:
        result = self.service.check(
            "draft-risky",
            "百分百有效",
            "可以根治皮肤问题。",
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.risk_level, "high")
        self.assertEqual({issue.term for issue in result.issues}, {"百分百有效", "根治"})


if __name__ == "__main__":
    unittest.main()
