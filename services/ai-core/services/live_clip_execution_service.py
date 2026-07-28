from __future__ import annotations

import asyncio
import re
from pathlib import Path

from app.schemas.live_clips import LiveClipExecutionResponse
from app.schemas.media_assets import MediaAssetCreate
from config import settings
from services.ffmpeg_service import FFmpegService, ffmpeg_service
from services.media_asset_service import MediaAssetService, media_asset_service
from services.media_storage_service import (
    MediaStorageService,
    media_storage_service,
)


_CLIP_URI_PATTERN = re.compile(
    r"^(?P<source>.+)#t=(?P<start>\d+(?:\.\d+)?),(?P<end>\d+(?:\.\d+)?)$"
)


class LiveClipExecutionService:
    def __init__(
        self,
        *,
        asset_service: MediaAssetService = media_asset_service,
        storage_service: MediaStorageService = media_storage_service,
        ffmpeg: FFmpegService = ffmpeg_service,
        max_duration_seconds: float = settings.LIVE_CLIP_MAX_DURATION_SECONDS,
    ) -> None:
        self.asset_service = asset_service
        self.storage_service = storage_service
        self.ffmpeg = ffmpeg
        self.max_duration_seconds = max_duration_seconds

    async def execute(self, planned_asset_id: str) -> LiveClipExecutionResponse:
        planned_asset = self.asset_service.get(planned_asset_id)
        if planned_asset is None:
            raise KeyError("切片计划素材不存在")
        if (
            planned_asset.asset_type != "video"
            or planned_asset.source != "live-clip-agent"
        ):
            raise ValueError("该素材不是直播切片 Agent 生成的候选计划")

        match = _CLIP_URI_PATTERN.fullmatch(planned_asset.uri)
        if match is None:
            raise ValueError("切片计划地址中没有有效的开始和结束时间")
        source_uri = match.group("source")
        start_seconds = float(match.group("start"))
        end_seconds = float(match.group("end"))
        clip_duration = end_seconds - start_seconds
        if clip_duration <= 0:
            raise ValueError("切片结束时间必须大于开始时间")
        if clip_duration > self.max_duration_seconds:
            raise ValueError(
                f"单个切片不能超过 {self.max_duration_seconds:g} 秒"
            )

        source_asset = self.asset_service.get_by_uri(source_uri)
        if source_asset is None:
            raise KeyError("找不到切片计划对应的源视频素材")
        if source_asset.asset_type != "video":
            raise ValueError("源素材不是视频")
        source_path = self.storage_service.resolve(source_asset.uri)
        if not source_path.is_file():
            raise FileNotFoundError("源视频文件不存在")

        source_duration = await asyncio.to_thread(
            self.ffmpeg.probe_duration,
            source_path,
        )
        if end_seconds > source_duration + 0.05:
            raise ValueError(
                f"切片结束时间 {end_seconds:g} 秒超过源视频时长 "
                f"{source_duration:.3f} 秒"
            )

        output_path = self.storage_service.reserve_temporary_path(".mp4")
        try:
            await asyncio.to_thread(
                self.ffmpeg.cut,
                source_path,
                output_path,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
            stored = self.storage_service.store_generated_file(
                output_path,
                content_type="video/mp4",
                original_filename=f"live-clip-{planned_asset.id[:8]}.mp4",
            )
        finally:
            Path(output_path).unlink(missing_ok=True)

        output_asset = self.asset_service.create(
            MediaAssetCreate(
                asset_type="video",
                title=planned_asset.title,
                uri=stored.uri,
                product_id=planned_asset.product_id,
                source="live-clip-agent-ffmpeg",
                tags=list(
                    dict.fromkeys([*planned_asset.tags, "物理切片", "待人工审核"])
                ),
                storage_provider="local",
                original_filename=stored.original_filename,
                content_type=stored.content_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
            )
        )
        return LiveClipExecutionResponse(
            planned_asset_id=planned_asset.id,
            source_asset_id=source_asset.id,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            duration_seconds=clip_duration,
            output_asset=output_asset,
        )


live_clip_execution_service = LiveClipExecutionService()
