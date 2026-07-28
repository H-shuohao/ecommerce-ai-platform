"""Run a real FFmpeg live-clip smoke test without touching production data."""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.schemas.media_assets import MediaAssetCreate
from database import Database
from services.ffmpeg_service import FFmpegService
from services.live_clip_execution_service import LiveClipExecutionService
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
        "sine=frequency=880:sample_rate=44100",
        "-t",
        "3",
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
    with tempfile.TemporaryDirectory(prefix="live-clip-e2e-") as temporary:
        storage = MediaStorageService(Path(temporary) / "assets", max_upload_mb=5)
        ffmpeg = FFmpegService(timeout_seconds=60)
        database = Database(":memory:")
        asset_service = MediaAssetService(MediaAssetRepository(database))

        source_temporary = storage.reserve_temporary_path(".mp4")
        generate_source_video(ffmpeg, source_temporary)
        stored_source = storage.store_generated_file(
            source_temporary,
            content_type="video/mp4",
            original_filename="live-replay-demo.mp4",
        )
        source_asset = asset_service.create(
            MediaAssetCreate(
                asset_type="video",
                title="直播回放测试视频",
                uri=stored_source.uri,
                product_id="P1001",
                source="ffmpeg-smoke-test",
                tags=["直播", "端到端测试"],
                storage_provider="local",
                original_filename=stored_source.original_filename,
                content_type=stored_source.content_type,
                size_bytes=stored_source.size_bytes,
                sha256=stored_source.sha256,
            )
        )
        planned_asset = asset_service.create(
            MediaAssetCreate(
                asset_type="video",
                title="直播高光测试片段",
                uri=f"{source_asset.uri}#t=0.5,2",
                product_id="P1001",
                source="live-clip-agent",
                tags=["直播切片", "P1001"],
            )
        )
        executor = LiveClipExecutionService(
            asset_service=asset_service,
            storage_service=storage,
            ffmpeg=ffmpeg,
            max_duration_seconds=10,
        )
        result = await executor.execute(planned_asset.id)
        output_path = storage.resolve(result.output_asset.uri)
        output_duration = ffmpeg.probe_duration(output_path)
        if not output_path.is_file():
            raise AssertionError("物理切片文件不存在")
        if not 1.4 <= output_duration <= 1.7:
            raise AssertionError(f"切片时长异常: {output_duration}")
        return {
            "status": "ok",
            "source_duration_seconds": ffmpeg.probe_duration(
                storage.resolve(source_asset.uri)
            ),
            "planned_range_seconds": [
                result.start_seconds,
                result.end_seconds,
            ],
            "output_duration_seconds": output_duration,
            "output_content_type": result.output_asset.content_type,
            "physical_cut_completed": result.physical_cut_completed,
            "human_review_required": result.human_review_required,
        }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))
