import unittest

from database import Database
from services.conversation_repository import ConversationRepository


class ConversationRepositoryTests(unittest.TestCase):
    def test_save_session_and_limit_recent_memory(self) -> None:
        db = Database(":memory:")
        repository = ConversationRepository(db)
        session_id = repository.ensure_session()

        for index in range(4):
            repository.append_exchange(
                session_id,
                f"问题{index}",
                f"回答{index}",
            )

        session = repository.get_session(session_id)
        recent = repository.get_recent_messages(session_id, limit=6)

        self.assertIsNotNone(session)
        self.assertEqual(len(session.messages), 8)
        self.assertEqual(len(recent), 6)
        self.assertEqual(recent[0]["content"], "问题1")
        self.assertEqual(recent[-1]["content"], "回答3")
        db.connection.close()

    def test_unknown_session_returns_none(self) -> None:
        db = Database(":memory:")
        repository = ConversationRepository(db)

        self.assertIsNone(repository.get_session("not-exists"))
        db.connection.close()

    def test_remember_current_product_without_polluting_messages(self) -> None:
        db = Database(":memory:")
        repository = ConversationRepository(db)
        session_id = repository.ensure_session("entity-memory")
        repository.append_exchange(
            session_id,
            "推荐适合油皮的商品",
            "为您推荐一款清爽防晒乳。",
        )

        repository.set_current_product_id(session_id, "p1001")

        self.assertEqual(repository.get_current_product_id(session_id), "P1001")
        session = repository.get_session(session_id)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.current_product_id, "P1001")
        self.assertNotIn("P1001", session.messages[-1].content)
        db.connection.close()


if __name__ == "__main__":
    unittest.main()
