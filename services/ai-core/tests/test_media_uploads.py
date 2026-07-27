import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from database import database
from main import app
from services.media_storage_service import MediaStorageService


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"portfolio-image-content"


class MediaUploadApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage_root = (
            Path(__file__).resolve().parents[1] / "data" / "test-assets"
        )
        self.storage = MediaStorageService(
            self.storage_root,
            max_upload_mb=1,
        )
        self.storage_patch = patch(
            "app.api.media_assets.media_storage_service",
            self.storage,
        )
        self.storage_patch.start()
        self.client = TestClient(app)
        self.asset_ids: set[str] = set()

    def tearDown(self) -> None:
        if self.asset_ids:
            placeholders = ",".join("?" for _ in self.asset_ids)
            with database.lock, database.connection:
                database.connection.execute(
                    f"DELETE FROM media_assets WHERE id IN ({placeholders})",
                    tuple(self.asset_ids),
                )
        for path in self.storage_root.glob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
        for path in self.storage.temp_root.glob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
        self.storage_patch.stop()

    def _upload_png(self):
        response = self.client.post(
            "/api/v1/assets/upload",
            data={
                "title": "防晒商品主图",
                "product_id": "P1001",
                "source": "unit-test",
                "tags": "防晒,主图,防晒",
            },
            files={"file": ("product.png", PNG_BYTES, "image/png")},
        )
        if response.status_code == 201:
            self.asset_ids.add(response.json()["id"])
        return response

    def test_upload_deduplicates_and_downloads_local_file(self) -> None:
        first = self._upload_png()
        second = self._upload_png()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.headers["X-Asset-Deduplicated"], "false")
        payload = first.json()
        self.assertEqual(payload["asset_type"], "image")
        self.assertEqual(payload["storage_provider"], "local")
        self.assertEqual(payload["content_type"], "image/png")
        self.assertEqual(payload["size_bytes"], len(PNG_BYTES))
        self.assertEqual(len(payload["sha256"]), 64)
        self.assertEqual(payload["tags"], ["防晒", "主图"])

        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.headers["X-Asset-Deduplicated"], "true")
        self.assertEqual(second.json()["id"], payload["id"])

        downloaded = self.client.get(
            f"/api/v1/assets/{payload['id']}/content"
        )
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, PNG_BYTES)
        self.assertEqual(downloaded.headers["content-type"], "image/png")

    def test_upload_rejects_mismatched_file_signature(self) -> None:
        response = self.client.post(
            "/api/v1/assets/upload",
            data={"title": "伪装图片"},
            files={"file": ("fake.png", b"not-a-png", "image/png")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Content-Type", response.json()["detail"])

    def test_upload_rejects_oversized_file(self) -> None:
        response = self.client.post(
            "/api/v1/assets/upload",
            data={"title": "过大文本"},
            files={
                "file": (
                    "large.txt",
                    b"x" * (1024 * 1024 + 1),
                    "text/plain",
                )
            },
        )

        self.assertEqual(response.status_code, 413)
        self.assertIn("1 MB", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
