"""Run the durable live-clip pipeline with the configured LLM and real FFmpeg."""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.schemas.live_clips import (
    LiveClipPipelineRequest,
    TranscriptSegment,
)
from app.schemas.media_assets import MediaAssetCreate
from database import Database
from services.ffmpeg_service import FFmpegService
from services.live_clip_agent_service import LiveClipAgentService
from services.live_clip_execution_service import LiveClipExecutionService
from services.live_clip_job_repository import LiveClipJobRepository
from services.live_clip_job_service import LiveClipJobService
from services.llm_service import llm_service
from services.media_asset_repository import MediaAssetRepository
from services.media_asset_service import MediaAssetService
from services.media_storage_service import MediaStorageService


def generate_source_video(ffmpeg: FFmpegService, target: Path) -> None:
    executable = ffmpeg._resolve_binary(ffmpeg.ffmpeg_binary)
    command = [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x1f7a5a:s=640x360:r=25",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=660:sample_rate=44100",
        "-t",
        "12",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(target),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "测试视频生成失败")


async def run() -> dict:
    with tempfile.TemporaryDirectory(prefix="live-clip-pipeline-") as temporary:
        database = Database(":memory:")
        storage = MediaStorageService(Path(temporary) / "assets", max_upload_mb=10)
        ffmpeg = FFmpegService(timeout_seconds=60)
        asset_service = MediaAssetService(MediaAssetRepository(database))
        repository = LiveClipJobRepository(database)
        planner = LiveClipAgentService(
            llm=llm_service,
            asset_service=asset_service,
        )
        executor = LiveClipExecutionService(
            asset_service=asset_service,
            storage_service=storage,
            ffmpeg=ffmpeg,
            max_duration_seconds=20,
        )
        pipeline = LiveClipJobService(
            repository=repository,
            planner=planner,
            executor=executor,
            asset_service=asset_service,
        )

        temporary_video = storage.reserve_temporary_path(".mp4")
        generate_source_video(ffmpeg, temporary_video)
        stored = storage.store_generated_file(
            temporary_video,
            content_type="video/mp4",
            original_filename="pipeline-live-replay.mp4",
        )
        source = asset_service.create(
            MediaAssetCreate(
                asset_type="video",
                title="异步流水线直播回放",
                uri=stored.uri,
                product_id="P1001",
                source="pipeline-smoke-test",
                tags=["直播", "异步流水线测试"],
                storage_provider="local",
                original_filename=stored.original_filename,
                content_type=stored.content_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
            )
        )
        request = LiveClipPipelineRequest(
            product_id="P1001",
            source_asset_id=source.id,
            transcript=[
                TranscriptSegment(
                    start_seconds=0,
                    end_seconds=4,
                    text="这款清爽防晒乳轻薄不黏腻，适合油性和混合性肤质。",
                ),
                TranscriptSegment(
                    start_seconds=4,
                    end_seconds=8,
                    text="它具有SPF50+防晒能力，适合日常通勤使用。",
                ),
                TranscriptSegment(
                    start_seconds=8,
                    end_seconds=12,
                    text="目前库存充足，售价129元，感兴趣可以进一步了解。",
                ),
            ],
            max_clips=1,
        )
        job = repository.create(
            request,
            idempotency_key="real-pipeline-smoke-test",
        )
        await pipeline.run(job.id)
        completed = repository.get(job.id)
        if completed is None or completed.status != "succeeded":
            error = completed.error if completed else "任务记录丢失"
            raise AssertionError(f"异步切片流水线失败: {error}")
        if len(completed.output_asset_ids) != 1:
            raise AssertionError("流水线没有生成预期的单个物理切片")
        output = asset_service.get(completed.output_asset_ids[0])
        if output is None:
            raise AssertionError("输出素材没有登记到素材中心")
        output_path = storage.resolve(output.uri)
        output_duration = ffmpeg.probe_duration(output_path)
        return {
            "status": completed.status,
            "job_id": completed.id,
            "attempt_count": completed.attempt_count,
            "transcript_segment_count": completed.transcript_segment_count,
            "planned_asset_count": len(completed.planned_asset_ids),
            "output_asset_count": len(completed.output_asset_ids),
            "output_duration_seconds": output_duration,
            "output_content_type": output.content_type,
            "human_review_required": True,
        }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
