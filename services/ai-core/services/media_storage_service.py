from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.schemas.media_assets import AssetType
from config import settings


class AssetFileError(ValueError):
    pass


class AssetFileTooLargeError(AssetFileError):
    pass


@dataclass(frozen=True)
class StoredAssetFile:
    uri: str
    path: Path
    asset_type: AssetType
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    deduplicated: bool


class MediaStorageService:
    URI_PREFIX = "local-asset://"
    _CONTENT_TYPES: dict[str, tuple[AssetType, str]] = {
        "image/jpeg": ("image", ".jpg"),
        "image/png": ("image", ".png"),
        "image/webp": ("image", ".webp"),
        "video/mp4": ("video", ".mp4"),
        "video/webm": ("video", ".webm"),
        "text/plain": ("text", ".txt"),
        "text/markdown": ("text", ".md"),
        "application/json": ("text", ".json"),
    }

    def __init__(
        self,
        root: str | Path = settings.ASSET_STORAGE_DIR,
        max_upload_mb: int = settings.ASSET_MAX_UPLOAD_MB,
    ) -> None:
        self.root = Path(root)
        self.max_bytes = max_upload_mb * 1024 * 1024
        self.root.mkdir(parents=True, exist_ok=True)
        self.temp_root = self.root / ".tmp"
        self.temp_root.mkdir(parents=True, exist_ok=True)

    async def store(self, upload: UploadFile) -> StoredAssetFile:
        content_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
        type_and_suffix = self._CONTENT_TYPES.get(content_type)
        if type_and_suffix is None:
            allowed = "、".join(sorted(self._CONTENT_TYPES))
            raise AssetFileError(f"不支持的文件类型: {content_type or '未知'}；允许: {allowed}")

        asset_type, suffix = type_and_suffix
        original_filename = self._safe_filename(upload.filename)
        temporary_path = self.temp_root / f"{uuid4().hex}.upload"
        digest = hashlib.sha256()
        size_bytes = 0
        first_bytes = b""

        try:
            with temporary_path.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > self.max_bytes:
                        raise AssetFileTooLargeError(
                            f"文件超过 {self.max_bytes // 1024 // 1024} MB 限制"
                        )
                    if not first_bytes:
                        first_bytes = chunk[:16]
                    digest.update(chunk)
                    output.write(chunk)

            if size_bytes == 0:
                raise AssetFileError("不能上传空文件")
            if not self._signature_matches(content_type, first_bytes):
                raise AssetFileError("文件内容与声明的 Content-Type 不匹配")

            sha256 = digest.hexdigest()
            target = self.root / f"{sha256}{suffix}"
            deduplicated = target.exists()
            if deduplicated:
                temporary_path.unlink(missing_ok=True)
            else:
                try:
                    temporary_path.replace(target)
                except FileExistsError:
                    temporary_path.unlink(missing_ok=True)
                    deduplicated = True

            return StoredAssetFile(
                uri=f"{self.URI_PREFIX}{target.name}",
                path=target,
                asset_type=asset_type,
                original_filename=original_filename,
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=sha256,
                deduplicated=deduplicated,
            )
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

    def reserve_temporary_path(self, suffix: str) -> Path:
        normalized_suffix = suffix.strip().lower()
        allowed_suffixes = {item[1] for item in self._CONTENT_TYPES.values()}
        if normalized_suffix not in allowed_suffixes:
            raise AssetFileError(f"不支持的临时文件扩展名: {normalized_suffix}")
        return self.temp_root / f"{uuid4().hex}{normalized_suffix}"

    def store_generated_file(
        self,
        temporary_path: str | Path,
        *,
        content_type: str,
        original_filename: str,
    ) -> StoredAssetFile:
        normalized_content_type = content_type.split(";", 1)[0].strip().lower()
        type_and_suffix = self._CONTENT_TYPES.get(normalized_content_type)
        if type_and_suffix is None:
            raise AssetFileError(f"不支持的生成文件类型: {normalized_content_type}")

        candidate = Path(temporary_path).resolve()
        if candidate.parent != self.temp_root.resolve():
            raise AssetFileError("生成文件必须位于受控临时目录")
        if not candidate.is_file():
            raise AssetFileError("生成文件不存在")

        asset_type, suffix = type_and_suffix
        digest = hashlib.sha256()
        size_bytes = 0
        first_bytes = b""
        try:
            with candidate.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > self.max_bytes:
                        raise AssetFileTooLargeError(
                            f"生成文件超过 {self.max_bytes // 1024 // 1024} MB 限制"
                        )
                    if not first_bytes:
                        first_bytes = chunk[:16]
                    digest.update(chunk)

            if size_bytes == 0:
                raise AssetFileError("生成文件不能为空")
            if not self._signature_matches(normalized_content_type, first_bytes):
                raise AssetFileError("生成文件内容与声明的 Content-Type 不匹配")

            sha256 = digest.hexdigest()
            target = self.root / f"{sha256}{suffix}"
            deduplicated = target.exists()
            if deduplicated:
                candidate.unlink(missing_ok=True)
            else:
                try:
                    candidate.replace(target)
                except FileExistsError:
                    candidate.unlink(missing_ok=True)
                    deduplicated = True

            return StoredAssetFile(
                uri=f"{self.URI_PREFIX}{target.name}",
                path=target,
                asset_type=asset_type,
                original_filename=self._safe_filename(original_filename),
                content_type=normalized_content_type,
                size_bytes=size_bytes,
                sha256=sha256,
                deduplicated=deduplicated,
            )
        except Exception:
            candidate.unlink(missing_ok=True)
            raise

    def resolve(self, uri: str) -> Path:
        if not uri.startswith(self.URI_PREFIX):
            raise AssetFileError("该素材只登记了外部地址，没有本地文件")
        filename = uri.removeprefix(self.URI_PREFIX)
        if not filename or Path(filename).name != filename:
            raise AssetFileError("素材文件地址无效")
        candidate = (self.root / filename).resolve()
        if candidate.parent != self.root.resolve():
            raise AssetFileError("素材文件地址越界")
        return candidate

    @staticmethod
    def _safe_filename(filename: str | None) -> str:
        normalized = (filename or "upload").replace("\\", "/").split("/")[-1].strip()
        return (normalized or "upload")[:255]

    @staticmethod
    def _signature_matches(content_type: str, head: bytes) -> bool:
        if content_type == "image/jpeg":
            return head.startswith(b"\xff\xd8\xff")
        if content_type == "image/png":
            return head.startswith(b"\x89PNG\r\n\x1a\n")
        if content_type == "image/webp":
            return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"
        if content_type == "video/mp4":
            return len(head) >= 12 and head[4:8] == b"ftyp"
        if content_type == "video/webm":
            return head.startswith(b"\x1a\x45\xdf\xa3")
        return True


media_storage_service = MediaStorageService()
