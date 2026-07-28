import unittest
from pathlib import Path
from uuid import uuid4

import httpx

from app.schemas.live_clips import TranscriptSegment
from services.asr_service import (
    ASRService,
    ASRUnavailableError,
    DisabledASRProvider,
    OpenAICompatibleASRProvider,
)
from services.media_storage_service import MediaStorageService


class FakeFFmpeg:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path]] = []

    def extract_audio(self, source: Path, target: Path) -> None:
        self.calls.append((source, target))
        target.write_bytes(b"RIFF-test-wave")


class RecordingProvider:
    def __init__(self) -> None:
        self.audio_existed = False
        self.language = ""

    async def transcribe(self, audio_path: Path, *, language: str):
        self.audio_existed = audio_path.is_file()
        self.language = language
        return [
            TranscriptSegment(
                start_seconds=0,
                end_seconds=2.5,
                text="自动识别的直播话术",
            )
        ]


class ASRServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.test_root = (
            Path(__file__).resolve().parents[1] / "data" / "test-asr-assets"
        )
        self.test_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for path in self.test_root.rglob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)

    async def test_extracts_audio_transcribes_and_cleans_temporary_file(self):
        source = self.test_root / f"{uuid4().hex}.mp4"
        source.write_bytes(b"video")
        storage = MediaStorageService(
            self.test_root / f"storage-{uuid4().hex}",
            max_upload_mb=1,
        )
        ffmpeg = FakeFFmpeg()
        provider = RecordingProvider()
        service = ASRService(
            provider=provider,
            ffmpeg=ffmpeg,
            storage_service=storage,
        )

        result = await service.transcribe_video(source, language="zh")

        self.assertEqual(result[0].text, "自动识别的直播话术")
        self.assertTrue(provider.audio_existed)
        self.assertEqual(provider.language, "zh")
        self.assertEqual(len(ffmpeg.calls), 1)
        self.assertFalse(ffmpeg.calls[0][1].exists())

    async def test_disabled_provider_explains_required_configuration(self):
        with self.assertRaisesRegex(ASRUnavailableError, "ASR_PROVIDER"):
            await DisabledASRProvider().transcribe(
                Path("unused.wav"),
                language="zh",
            )

    async def test_openai_compatible_provider_parses_timestamp_segments(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            self.assertIn("multipart/form-data", request.headers["content-type"])
            return httpx.Response(
                200,
                json={
                    "text": "第一句。第二句。",
                    "segments": [
                        {"start": 0.0, "end": 1.5, "text": "第一句。"},
                        {"start": 1.5, "end": 3.0, "text": "第二句。"},
                    ],
                },
            )

        provider = OpenAICompatibleASRProvider(
            api_url="https://asr.example.test/v1/audio/transcriptions",
            api_key="test-key",
            model="whisper-test",
            transport=httpx.MockTransport(handler),
        )
        audio = self.test_root / f"{uuid4().hex}.wav"
        audio.write_bytes(b"RIFF-test-wave")

        result = await provider.transcribe(audio, language="zh")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].start_seconds, 0)
        self.assertEqual(result[1].end_seconds, 3)
        self.assertEqual(result[1].text, "第二句。")


if __name__ == "__main__":
    unittest.main()
