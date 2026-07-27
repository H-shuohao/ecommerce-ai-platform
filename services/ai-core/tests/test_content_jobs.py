import unittest
from unittest.mock import patch

from app.schemas.content_agents import ContentGenerateResponse
from fastapi.testclient import TestClient
from database import Database
from database import database
from main import app
from services.content_draft_repository import ContentDraftRepository
from services.content_job_repository import ContentJobRepository, content_job_repository
from services.content_job_service import ContentJobService


class SuccessfulGenerator:
    async def generate(self, product_id, platform, tone):
        return ContentGenerateResponse(
            product_id=product_id,
            platform=platform,
            title="通勤防晒内容草稿",
            body="根据已核验的商品事实生成的测试正文。",
            hashtags=["防晒", "通勤"],
            source_facts={"id": product_id, "price": 129},
        )


class FailingGenerator:
    async def generate(self, product_id, platform, tone):
        raise RuntimeError("模型服务暂时不可用")


class ContentJobRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.repository = ContentJobRepository(self.db)

    def tearDown(self) -> None:
        self.db.connection.close()

    def test_idempotency_key_reuses_existing_job(self) -> None:
        first = self.repository.create(
            product_id="P1001",
            platform="xiaohongshu",
            tone="friendly",
            idempotency_key="content-request-001",
        )
        second = self.repository.create(
            product_id="P1001",
            platform="xiaohongshu",
            tone="friendly",
            idempotency_key="content-request-001",
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.repository.list()), 1)

    def test_failed_job_can_be_queued_for_retry(self) -> None:
        created = self.repository.create(
            product_id="P1001",
            platform="douyin",
            tone="energetic",
        )
        running = self.repository.mark_running(created.id)
        failed = self.repository.mark_failed(created.id, "temporary failure")
        queued = self.repository.queue_retry(created.id)

        self.assertEqual(running.status, "running")
        self.assertEqual(running.attempt_count, 1)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error, "temporary failure")
        self.assertEqual(queued.status, "queued")
        self.assertIsNone(queued.error)

    def test_running_job_is_requeued_after_restart(self) -> None:
        created = self.repository.create(
            product_id="P1001",
            platform="wechat",
            tone="professional",
        )
        running = self.repository.mark_running(created.id)

        self.assertEqual(running.status, "running")
        self.assertEqual(self.repository.requeue_interrupted(), 1)
        recovered = self.repository.get(created.id)
        self.assertEqual(recovered.status, "queued")
        self.assertIsNone(recovered.started_at)
        self.assertEqual(recovered.error, "服务重启，任务已重新排队")


class ContentJobServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = Database(":memory:")
        self.repository = ContentJobRepository(self.db)
        self.draft_repository = ContentDraftRepository(self.db)

    async def asyncTearDown(self) -> None:
        self.db.connection.close()

    async def test_run_persists_generated_draft_and_success_status(self) -> None:
        service = ContentJobService(
            repository=self.repository,
            generator=SuccessfulGenerator(),
            draft_repository=self.draft_repository,
        )
        job = self.repository.create(
            product_id="P1001",
            platform="xiaohongshu",
            tone="friendly",
        )

        await service.run(job.id)

        completed = self.repository.get(job.id)
        self.assertEqual(completed.status, "succeeded")
        self.assertEqual(completed.attempt_count, 1)
        self.assertIsNotNone(completed.draft_id)
        draft = self.draft_repository.get(completed.draft_id)
        self.assertEqual(draft.product_id, "P1001")
        self.assertEqual(draft.status, "pending")

    async def test_run_records_failure_without_losing_job(self) -> None:
        service = ContentJobService(
            repository=self.repository,
            generator=FailingGenerator(),
            draft_repository=self.draft_repository,
        )
        job = self.repository.create(
            product_id="P1001",
            platform="wechat",
            tone="professional",
        )

        await service.run(job.id)

        failed = self.repository.get(job.id)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.attempt_count, 1)
        self.assertIn("模型服务暂时不可用", failed.error)
        self.assertIsNone(failed.draft_id)


class ContentJobApiTests(unittest.TestCase):
    @staticmethod
    def _delete_job(job_id: str) -> None:
        with database.lock, database.connection:
            database.connection.execute(
                "DELETE FROM content_generation_jobs WHERE id = ?",
                (job_id,),
            )

    @patch("app.api.content_agents.content_job_service.submit")
    def test_submit_and_query_job_contract(self, submit) -> None:
        job = content_job_repository.create(
            product_id="P1001",
            platform="xiaohongshu",
            tone="friendly",
            idempotency_key="api-content-job-test",
        )
        self.addCleanup(self._delete_job, job.id)
        submit.return_value = job
        client = TestClient(app)

        created = client.post(
            "/api/v1/agents/content/jobs",
            headers={"X-Idempotency-Key": "api-content-job-test"},
            json={
                "product_id": "P1001",
                "platform": "xiaohongshu",
                "tone": "friendly",
            },
        )
        queried = client.get(f"/api/v1/agents/content/jobs/{job.id}")

        self.assertEqual(created.status_code, 202)
        self.assertEqual(created.json()["id"], job.id)
        self.assertEqual(created.json()["status"], "queued")
        self.assertEqual(queried.status_code, 200)
        self.assertEqual(queried.json()["id"], job.id)
        submit.assert_called_once_with(
            product_id="P1001",
            platform="xiaohongshu",
            tone="friendly",
            idempotency_key="api-content-job-test",
        )

        with database.lock, database.connection:
            database.connection.execute(
                "DELETE FROM content_generation_jobs WHERE id = ?",
                (job.id,),
            )


if __name__ == "__main__":
    unittest.main()
