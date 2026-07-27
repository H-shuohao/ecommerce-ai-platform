from __future__ import annotations

import asyncio

from app.schemas.content_agents import (
    ContentGenerationJob,
    ContentPlatform,
    ContentTone,
)
from services.content_agent_service import ContentAgentService, content_agent_service
from services.content_draft_repository import (
    ContentDraftRepository,
    content_draft_repository,
)
from services.content_job_repository import ContentJobRepository, content_job_repository


class ContentJobService:
    def __init__(
        self,
        repository: ContentJobRepository = content_job_repository,
        generator: ContentAgentService = content_agent_service,
        draft_repository: ContentDraftRepository = content_draft_repository,
    ) -> None:
        self.repository = repository
        self.generator = generator
        self.draft_repository = draft_repository
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(
        self,
        *,
        product_id: str,
        platform: ContentPlatform,
        tone: ContentTone,
        idempotency_key: str | None = None,
    ) -> ContentGenerationJob:
        job = self.repository.create(
            product_id=product_id,
            platform=platform,
            tone=tone,
            idempotency_key=idempotency_key,
        )
        if job.status == "queued":
            self._schedule(job.id)
        return job

    def retry(self, job_id: str) -> ContentGenerationJob:
        existing = self.repository.get(job_id)
        if existing is None:
            raise KeyError("内容生成任务不存在")
        if existing.status != "failed":
            raise ValueError("只有失败的任务可以重试")
        if existing.attempt_count >= existing.max_attempts:
            raise ValueError("任务已达到最大重试次数")
        queued = self.repository.queue_retry(job_id)
        if queued is None:
            raise ValueError("任务当前状态不允许重试")
        self._schedule(job_id)
        return queued

    def recover_incomplete(self) -> int:
        """Requeue interrupted work and resume durable queued jobs on startup."""
        interrupted = self.repository.requeue_interrupted()
        queued_jobs = self.repository.list(status="queued", limit=100)
        for job in queued_jobs:
            self._schedule(job.id)
        return interrupted + len(queued_jobs)

    async def shutdown(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _schedule(self, job_id: str) -> None:
        if any(
            not task.done() and task.get_name() == f"content-job:{job_id}"
            for task in self._tasks
        ):
            return
        task = asyncio.create_task(
            self.run(job_id),
            name=f"content-job:{job_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def run(self, job_id: str) -> None:
        job = self.repository.mark_running(job_id)
        if job is None:
            return
        try:
            content = await self.generator.generate(
                product_id=job.product_id,
                platform=job.platform,
                tone=job.tone,
            )
            draft_id = self.draft_repository.create(content, job.tone)
            self.repository.mark_succeeded(job_id, draft_id)
        except Exception as error:
            message = str(error).strip() or type(error).__name__
            self.repository.mark_failed(job_id, message)


content_job_service = ContentJobService()
