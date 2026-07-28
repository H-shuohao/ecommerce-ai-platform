from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from config import settings


class FFmpegUnavailableError(RuntimeError):
    pass


class FFmpegProcessingError(RuntimeError):
    pass


class FFmpegService:
    def __init__(
        self,
        ffmpeg_binary: str = settings.FFMPEG_BINARY,
        ffprobe_binary: str = settings.FFPROBE_BINARY,
        timeout_seconds: float = settings.FFMPEG_TIMEOUT_SECONDS,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.ffprobe_binary = ffprobe_binary
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _resolve_binary(binary: str) -> str:
        resolved = shutil.which(binary)
        if resolved is None:
            raise FFmpegUnavailableError(
                f"没有找到 {binary}，请安装 FFmpeg 或检查环境变量配置"
            )
        return resolved

    def probe_duration(self, source: Path) -> float:
        ffprobe = self._resolve_binary(self.ffprobe_binary)
        command = [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source),
        ]
        completed = self._run(command, "读取视频时长")
        try:
            duration = float(completed.stdout.strip())
        except ValueError as error:
            raise FFmpegProcessingError("FFprobe 没有返回有效的视频时长") from error
        if duration <= 0:
            raise FFmpegProcessingError("源视频时长无效")
        return duration

    def cut(
        self,
        source: Path,
        target: Path,
        *,
        start_seconds: float,
        end_seconds: float,
    ) -> None:
        if start_seconds < 0 or end_seconds <= start_seconds:
            raise ValueError("切片结束时间必须大于开始时间")
        ffmpeg = self._resolve_binary(self.ffmpeg_binary)
        duration = end_seconds - start_seconds
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{start_seconds:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(target),
        ]
        self._run(command, "裁剪视频")
        if not target.is_file() or target.stat().st_size == 0:
            raise FFmpegProcessingError("FFmpeg 没有生成有效的切片文件")

    def extract_audio(self, source: Path, target: Path) -> None:
        ffmpeg = self._resolve_binary(self.ffmpeg_binary)
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
        self._run(command, "提取直播回放音频")
        if not target.is_file() or target.stat().st_size == 0:
            raise FFmpegProcessingError("FFmpeg 没有生成有效的音频文件")

    def _run(
        self,
        command: list[str],
        action: str,
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise FFmpegProcessingError(
                f"{action}超时（限制 {self.timeout_seconds:g} 秒）"
            ) from error
        except OSError as error:
            raise FFmpegProcessingError(f"{action}失败: {error}") from error
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise FFmpegProcessingError(
                f"{action}失败: {detail[:500] or '未知 FFmpeg 错误'}"
            )
        return completed


ffmpeg_service = FFmpegService()
