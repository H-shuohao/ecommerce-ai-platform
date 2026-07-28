from __future__ import annotations

import asyncio

from app.schemas.live_clips import (
    LiveClipPipelineJob,
    LiveClipPipelineRequest,
    LiveClipPlanRequest,
)
from services.asr_service import ASRService, asr_service
from services.live_clip_agent_service import LiveClipAgentService, live_clip_agent_service
from services.live_clip_execution_service import (
    LiveClipExecutionService,
    live_clip_execution_service,
)
from services.live_clip_job_repository import (
    LiveClipJobRepository,
    live_clip_job_repository,
)
from services.media_asset_service import MediaAssetService, media_asset_service
from services.media_storage_service import (
    MediaStorageService,
    media_storage_service,
)


class LiveClipJobService:
    def __init__(
        self,
        *,
        repository: LiveClipJobRepository = live_clip_job_repository,
        planner: LiveClipAgentService = live_clip_agent_service,
        executor: LiveClipExecutionService = live_clip_execution_service,
        asset_service: MediaAssetService = media_asset_service,
        transcriber: ASRService = asr_service,
        storage_service: MediaStorageService = media_storage_service,
    ) -> None:
        self.repository = repository
        self.planner = planner
        self.executor = executor
        self.asset_service = asset_service
        self.transcriber = transcriber
        self.storage_service = storage_service
        self._tasks: set[asyncio.Task[None]] = set()

    def submit(
        self,
        request: LiveClipPipelineRequest,
        *,
        idempotency_key: str | None = None,
    ) -> LiveClipPipelineJob:
        self._validate_source(request)
        job = self.repository.create(
            request,
            idempotency_key=idempotency_key,
        )
        if job.status == "queued":
            self._schedule(job.id)
        return job

    def retry(self, job_id: str) -> LiveClipPipelineJob:
        existing = self.repository.get(job_id)
        if existing is None:
            raise KeyError("直播切片流水线任务不存在")
        if existing.status != "failed":
            raise ValueError("只有失败的直播切片任务可以重试")
        if existing.attempt_count >= existing.max_attempts:
            raise ValueError("直播切片任务已经达到最大重试次数")
        queued = self.repository.queue_retry(job_id)
        if queued is None:
            raise ValueError("直播切片任务当前状态不允许重试")
        self._schedule(job_id)
        return queued

    def recover_incomplete(self) -> int:
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
        task_name = f"live-clip-job:{job_id}"
        if any(
            not task.done() and task.get_name() == task_name
            for task in self._tasks
        ):
            return
        task = asyncio.create_task(self.run(job_id), name=task_name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _validate_source(self, request: LiveClipPipelineRequest):
        source = self.asset_service.get(request.source_asset_id)
        if source is None:
            raise KeyError("直播回放源素材不存在")
        if source.asset_type != "video":
            raise ValueError("流水线源素材必须是视频")
        if source.storage_provider != "local":
            raise ValueError("流水线当前只处理通过素材中心上传的本地视频")
        if source.product_id not in {None, request.product_id}:
            raise ValueError("源素材关联的商品与任务商品不一致")
        return source

    async def run(self, job_id: str) -> None:
        job = self.repository.mark_running(job_id)
        if job is None:
            return
        try:
            request = self.repository.load_request(job_id)
            if request is None:
                raise RuntimeError("找不到直播切片任务请求")
            source = self._validate_source(request)

            if not request.transcript:
                source_path = self.storage_service.resolve(source.uri)
                transcript = await self.transcriber.transcribe_video(
                    source_path,
                    language=request.transcript_language,
                )
                saved = self.repository.save_transcript(job_id, transcript)
                if saved is None:
                    raise RuntimeError("ASR 转写进度保存失败")
                request = self.repository.load_request(job_id)
                if request is None or not request.transcript:
                    raise RuntimeError("ASR 转写结果读取失败")
                job = saved

            planned_asset_ids = list(job.planned_asset_ids)
            if not planned_asset_ids:
                plan = await self.planner.plan(
                    LiveClipPlanRequest(
                        product_id=request.product_id,
                        video_uri=source.uri,
                        transcript=request.transcript,
                        max_clips=request.max_clips,
                    )
                )
                planned_asset_ids = [clip.asset_id for clip in plan.clips]
                saved = self.repository.save_plan(job_id, planned_asset_ids)
                if saved is None:
                    raise RuntimeError("切片计划进度保存失败")
                job = saved

            completed_count = len(job.output_asset_ids)
            if completed_count > len(planned_asset_ids):
                raise RuntimeError("直播切片任务进度数据不一致")
            for planned_asset_id in planned_asset_ids[completed_count:]:
                result = await self.executor.execute(planned_asset_id)
                saved = self.repository.append_output(
                    job_id,
                    result.output_asset.id,
                )
                if saved is None:
                    raise RuntimeError("物理切片进度保存失败")
            self.repository.mark_succeeded(job_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            message = str(error).strip() or type(error).__name__
            self.repository.mark_failed(job_id, message)


live_clip_job_service = LiveClipJobService()
