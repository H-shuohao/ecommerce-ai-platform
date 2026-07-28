from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

import httpx

from app.schemas.live_clips import TranscriptSegment
from config import settings
from services.ffmpeg_service import FFmpegService, ffmpeg_service
from services.media_storage_service import MediaStorageService, media_storage_service


class ASRUnavailableError(RuntimeError):
    pass


class ASRTranscriptionError(RuntimeError):
    pass


class ASRProvider(Protocol):
    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str,
    ) -> list[TranscriptSegment]: ...


class OpenAICompatibleASRProvider:
    def __init__(
        self,
        *,
        api_url: str = settings.ASR_API_URL,
        api_key: str = settings.ASR_API_KEY,
        model: str = settings.ASR_MODEL,
        timeout_seconds: float = settings.ASR_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str,
    ) -> list[TranscriptSegment]:
        if not self.api_url or not self.api_key:
            raise ASRUnavailableError(
                "批量 ASR 尚未配置：请设置 ASR_API_URL 和 ASR_API_KEY"
            )
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {
            "model": self.model,
            "language": language,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                with audio_path.open("rb") as audio:
                    response = await client.post(
                        self.api_url,
                        headers=headers,
                        data=data,
                        files={"file": (audio_path.name, audio, "audio/wav")},
                    )
        except (OSError, httpx.HTTPError) as error:
            raise ASRTranscriptionError(f"调用批量 ASR 失败: {error}") from error
        if response.status_code >= 400:
            detail = response.text.strip()
            raise ASRTranscriptionError(
                f"批量 ASR 返回 HTTP {response.status_code}: "
                f"{detail[:500] or '未知错误'}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise ASRTranscriptionError("批量 ASR 没有返回有效 JSON") from error

        raw_segments = payload.get("segments")
        if not isinstance(raw_segments, list):
            raise ASRTranscriptionError(
                "批量 ASR 未返回 segments；请启用 verbose_json 分段时间戳"
            )
        segments: list[TranscriptSegment] = []
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            try:
                segment = TranscriptSegment(
                    start_seconds=float(item["start"]),
                    end_seconds=float(item["end"]),
                    text=text,
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ASRTranscriptionError(
                    "批量 ASR 返回了无效的分段时间戳"
                ) from error
            segments.append(segment)
        if not segments:
            raise ASRTranscriptionError("批量 ASR 没有识别出有效语音")
        return segments


class DisabledASRProvider:
    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str,
    ) -> list[TranscriptSegment]:
        del audio_path, language
        raise ASRUnavailableError(
            "直播回放没有手工转写，且批量 ASR 未启用；"
            "请配置 ASR_PROVIDER=openai-compatible"
        )


def build_asr_provider() -> ASRProvider:
    if settings.ASR_PROVIDER == "openai-compatible":
        return OpenAICompatibleASRProvider()
    if settings.ASR_PROVIDER == "disabled":
        return DisabledASRProvider()
    raise ASRUnavailableError(
        f"不支持的 ASR_PROVIDER: {settings.ASR_PROVIDER}"
    )


class ASRService:
    def __init__(
        self,
        *,
        provider: ASRProvider | None = None,
        ffmpeg: FFmpegService = ffmpeg_service,
        storage_service: MediaStorageService = media_storage_service,
    ) -> None:
        self.provider = provider or build_asr_provider()
        self.ffmpeg = ffmpeg
        self.storage_service = storage_service

    async def transcribe_video(
        self,
        source_path: Path,
        *,
        language: str = "zh",
    ) -> list[TranscriptSegment]:
        if not source_path.is_file():
            raise FileNotFoundError("ASR 找不到直播回放源文件")
        audio_path = self.storage_service.reserve_temporary_path(".wav")
        try:
            await asyncio.to_thread(
                self.ffmpeg.extract_audio,
                source_path,
                audio_path,
            )
            return await self.provider.transcribe(
                audio_path,
                language=language,
            )
        finally:
            audio_path.unlink(missing_ok=True)


asr_service = ASRService()
