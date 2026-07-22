import unittest

from app.schemas.content_agents import ContentGenerateResponse
from database import Database
from services.content_draft_repository import ContentDraftRepository


class ContentDraftRepositoryTests(unittest.TestCase):
    def test_create_and_review_draft(self) -> None:
        db = Database(":memory:")
        repository = ContentDraftRepository(db)
        content = ContentGenerateResponse(
            product_id="P1001",
            platform="xiaohongshu",
            title="测试标题",
            body="测试正文",
            hashtags=["防晒"],
            source_facts={"id": "P1001", "price": 129},
        )

        draft_id = repository.create(content, "friendly")
        pending = repository.get(draft_id)
        approved = repository.review(draft_id, "approved", "事实核验通过")
        edited = repository.update(
            draft_id,
            title="人工修改后的标题",
        )

        self.assertEqual(pending.status, "pending")
        self.assertTrue(pending.human_review_required)
        self.assertEqual(approved.status, "approved")
        self.assertFalse(approved.human_review_required)
        self.assertEqual(approved.review_comment, "事实核验通过")
        self.assertEqual(edited.title, "人工修改后的标题")
        self.assertEqual(edited.status, "pending")
        self.assertIsNone(edited.review_comment)
        db.connection.close()


if __name__ == "__main__":
    unittest.main()
