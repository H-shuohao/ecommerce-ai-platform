import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.schemas.live_clips import (
    LiveClip,
    LiveClipExecutionResponse,
    LiveClipPipelineRequest,
    LiveClipPlanResponse,
    TranscriptSegment,
)
from app.schemas.media_assets import MediaAsset, MediaAssetCreate
from database import Database, database
from main import app
from services.live_clip_job_repository import (
    LiveClipJobRepository,
    live_clip_job_repository,
)
from services.live_clip_job_service import LiveClipJobService
from services.media_asset_repository import MediaAssetRepository
from services.media_asset_service import media_asset_service


def pipeline_request(
    source_asset_id: str = "source-asset-1",
) -> LiveClipPipelineRequest:
    return LiveClipPipelineRequest(
        product_id="P1001",
        source_asset_id=source_asset_id,
        transcript=[
            TranscriptSegment(
                start_seconds=0,
                end_seconds=8,
                text="这款防晒轻薄不黏腻，适合日常通勤。",
            ),
            TranscriptSegment(
                start_seconds=8,
                end_seconds=16,
                text="现在库存充足，可以正常选购。",
            ),
        ],
        max_clips=2,
    )


def media_asset(
    asset_id: str,
    *,
    source: str = "unit-test",
    uri: str | None = None,
) -> MediaAsset:
    return MediaAsset(
        id=asset_id,
        asset_type="video",
        title=asset_id,
        uri=uri or f"asset://local/{asset_id}.mp4",
        product_id="P1001",
        source=source,
        tags=["直播"],
        storage_provider="local",
        original_filename=f"{asset_id}.mp4",
        content_type="video/mp4",
        size_bytes=128,
        sha256="a" * 64,
        status="active",
        created_at="2026-07-28T00:00:00+00:00",
        updated_at="2026-07-28T00:00:00+00:00",
    )


class FakeAssetService:
    def __init__(self, source_asset_id: str) -> None:
        self.source = media_asset(source_asset_id)

    def get(self, asset_id: str):
        return self.source if asset_id == self.source.id else None


class FakePlanner:
    def __init__(self) -> None:
        self.call_count = 0

    async def plan(self, request):
        self.call_count += 1
        self.last_request = request
        return LiveClipPlanResponse(
            product_id=request.product_id,
            source_video_uri=request.video_uri,
            clips=[
                LiveClip(
                    title="卖点片段",
                    start_seconds=0,
                    end_seconds=8,
                    reason="卖点完整",
                    asset_id="plan-1",
                    clip_uri=f"{request.video_uri}#t=0,8",
                ),
                LiveClip(
                    title="库存片段",
                    start_seconds=8,
                    end_seconds=16,
                    reason="购买信息完整",
                    asset_id="plan-2",
                    clip_uri=f"{request.video_uri}#t=8,16",
                ),
            ],
        )


class ResumableExecutor:
    def __init__(self, source_asset_id: str) -> None:
        self.calls: list[str] = []
        self.failed_once = False
        self.source_asset_id = source_asset_id

    async def execute(self, planned_asset_id: str):
        self.calls.append(planned_asset_id)
        if planned_asset_id == "plan-2" and not self.failed_once:
            self.failed_once = True
            raise RuntimeError("模拟第二个片段转码失败")
        return LiveClipExecutionResponse(
            planned_asset_id=planned_asset_id,
            source_asset_id=self.source_asset_id,
            start_seconds=0,
            end_seconds=8,
            duration_seconds=8,
            output_asset=media_asset(
                f"output-{planned_asset_id}",
                source="live-clip-agent-ffmpeg",
            ),
        )


class FakeTranscriber:
    def __init__(self) -> None:
        self.call_count = 0

    async def transcribe_video(self, source_path, *, language):
        self.call_count += 1
        return [
            TranscriptSegment(
                start_seconds=0,
                end_seconds=8,
                text=f"ASR 自动转写，语言为 {language}",
            ),
            TranscriptSegment(
                start_seconds=8,
                end_seconds=16,
                text="第二段直播话术",
            ),
        ]


class FakeStorage:
    def __init__(self, path) -> None:
        self.path = path

    def resolve(self, uri):
        return self.path


class LiveClipJobRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.repository = LiveClipJobRepository(self.db)
        self.source = MediaAssetRepository(self.db).create(
            MediaAssetCreate(
                asset_type="video",
                title="测试直播源视频",
                uri="asset://local/repository-test-source.mp4",
                product_id="P1001",
                source="unit-test",
                tags=["直播"],
            )
        )

    def tearDown(self) -> None:
        self.db.connection.close()

    def test_idempotency_reuses_same_request(self) -> None:
        request = pipeline_request(self.source.id)
        first = self.repository.create(request, idempotency_key="clip-request-1")
        second = self.repository.create(request, idempotency_key="clip-request-1")

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.repository.list()), 1)

    def test_idempotency_rejects_different_request(self) -> None:
        first_request = pipeline_request(self.source.id)
        second_request = first_request.model_copy(update={"max_clips": 1})
        self.repository.create(first_request, idempotency_key="clip-request-2")

        with self.assertRaisesRegex(ValueError, "已经用于另一个"):
            self.repository.create(
                second_request,
                idempotency_key="clip-request-2",
            )

    def test_running_job_is_requeued_without_losing_progress(self) -> None:
        created = self.repository.create(pipeline_request(self.source.id))
        self.repository.mark_running(created.id)
        self.repository.save_plan(created.id, ["plan-1", "plan-2"])
        self.repository.append_output(created.id, "output-plan-1")

        self.assertEqual(self.repository.requeue_interrupted(), 1)
        recovered = self.repository.get(created.id)
        self.assertEqual(recovered.status, "queued")
        self.assertEqual(recovered.stage, "queued")
        self.assertEqual(recovered.planned_asset_ids, ["plan-1", "plan-2"])
        self.assertEqual(recovered.output_asset_ids, ["output-plan-1"])


class LiveClipJobServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = Database(":memory:")
        self.repository = LiveClipJobRepository(self.db)
        self.source = MediaAssetRepository(self.db).create(
            MediaAssetCreate(
                asset_type="video",
                title="测试直播源视频",
                uri="asset://local/service-test-source.mp4",
                product_id="P1001",
                source="unit-test",
                tags=["直播"],
            )
        )

    async def asyncTearDown(self) -> None:
        self.db.connection.close()

    async def test_retry_continues_from_last_completed_clip(self) -> None:
        planner = FakePlanner()
        executor = ResumableExecutor(self.source.id)
        service = LiveClipJobService(
            repository=self.repository,
            planner=planner,
            executor=executor,
            asset_service=FakeAssetService(self.source.id),
        )
        job = self.repository.create(pipeline_request(self.source.id))

        await service.run(job.id)
        failed = self.repository.get(job.id)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.stage, "failed")
        self.assertEqual(failed.planned_asset_ids, ["plan-1", "plan-2"])
        self.assertEqual(failed.output_asset_ids, ["output-plan-1"])

        self.repository.queue_retry(job.id)
        await service.run(job.id)
        completed = self.repository.get(job.id)

        self.assertEqual(completed.status, "succeeded")
        self.assertEqual(completed.stage, "completed")
        self.assertEqual(
            completed.output_asset_ids,
            ["output-plan-1", "output-plan-2"],
        )
        self.assertEqual(planner.call_count, 1)
        self.assertEqual(executor.calls, ["plan-1", "plan-2", "plan-2"])

    async def test_empty_transcript_runs_asr_once_and_persists_result(self):
        planner = FakePlanner()
        executor = ResumableExecutor(self.source.id)
        transcriber = FakeTranscriber()
        request = pipeline_request(self.source.id).model_copy(
            update={"transcript": []}
        )
        service = LiveClipJobService(
            repository=self.repository,
            planner=planner,
            executor=executor,
            asset_service=FakeAssetService(self.source.id),
            transcriber=transcriber,
            storage_service=FakeStorage("source.mp4"),
        )
        job = self.repository.create(request)

        await service.run(job.id)
        failed = self.repository.get(job.id)

        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.stage, "failed")
        self.assertEqual(failed.transcript_source, "asr")
        self.assertEqual(failed.transcript_segment_count, 2)
        self.assertEqual(transcriber.call_count, 1)
        self.assertEqual(len(planner.last_request.transcript), 2)

        self.repository.queue_retry(job.id)
        await service.run(job.id)
        completed = self.repository.get(job.id)

        self.assertEqual(completed.status, "succeeded")
        self.assertEqual(completed.stage, "completed")
        self.assertEqual(transcriber.call_count, 1)


class LiveClipJobApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = media_asset_service.create(
            MediaAssetCreate(
                asset_type="video",
                title="流水线API测试源视频",
                uri="https://example.com/live-clip-job-api-test.mp4",
                product_id="P1001",
                source="unit-test",
                tags=["直播"],
            )
        )
        self.request = LiveClipPipelineRequest(
            product_id="P1001",
            source_asset_id=self.source.id,
            transcript=[
                TranscriptSegment(
                    start_seconds=0,
                    end_seconds=10,
                    text="测试直播转写。",
                )
            ],
            max_clips=1,
        )

    def tearDown(self) -> None:
        with database.lock, database.connection:
            database.connection.execute(
                "DELETE FROM live_clip_pipeline_jobs WHERE source_asset_id = ?",
                (self.source.id,),
            )
            database.connection.execute(
                "DELETE FROM media_assets WHERE id = ?",
                (self.source.id,),
            )

    @patch("app.api.live_clips.live_clip_job_service.submit")
    def test_submit_and_query_pipeline_contract(self, submit) -> None:
        job = live_clip_job_repository.create(
            self.request,
            idempotency_key="api-live-clip-job-test",
        )
        submit.return_value = job
        client = TestClient(app)

        created = client.post(
            "/api/v1/agents/live-clips/pipelines",
            headers={"X-Idempotency-Key": "api-live-clip-job-test"},
            json=self.request.model_dump(mode="json"),
        )
        queried = client.get(
            f"/api/v1/agents/live-clips/pipelines/{job.id}"
        )

        self.assertEqual(created.status_code, 202)
        self.assertEqual(created.json()["id"], job.id)
        self.assertEqual(created.json()["status"], "queued")
        self.assertEqual(queried.status_code, 200)
        self.assertEqual(queried.json()["source_asset_id"], self.source.id)
        submit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
