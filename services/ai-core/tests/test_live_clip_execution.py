import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.schemas.media_assets import MediaAssetCreate
from database import database
from main import app
from services.live_clip_execution_service import live_clip_execution_service
from services.media_asset_service import media_asset_service
from services.media_storage_service import MediaStorageService


def mp4_bytes(label: str) -> bytes:
    return b"\x00\x00\x00\x18ftypisom" + label.encode("utf-8")


class FakeFFmpeg:
    def __init__(self, duration: float = 20.0) -> None:
        self.duration = duration
        self.calls: list[tuple[float, float]] = []

    def probe_duration(self, source: Path) -> float:
        if not source.is_file():
            raise AssertionError("测试源视频不存在")
        return self.duration

    def cut(
        self,
        source: Path,
        target: Path,
        *,
        start_seconds: float,
        end_seconds: float,
    ) -> None:
        self.calls.append((start_seconds, end_seconds))
        target.write_bytes(mp4_bytes(f"clip-{start_seconds}-{end_seconds}"))


class LiveClipExecutionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage_root = (
            Path(__file__).resolve().parents[1] / "data" / "test-live-clip-assets"
        )
        self.storage = MediaStorageService(self.storage_root, max_upload_mb=1)
        self.fake_ffmpeg = FakeFFmpeg()
        self.patches = [
            patch(
                "app.api.media_assets.media_storage_service",
                self.storage,
            ),
            patch.object(
                live_clip_execution_service,
                "storage_service",
                self.storage,
            ),
            patch.object(
                live_clip_execution_service,
                "ffmpeg",
                self.fake_ffmpeg,
            ),
        ]
        for item in self.patches:
            item.start()
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
        for item in reversed(self.patches):
            item.stop()

    def _upload_source(self) -> dict:
        marker = uuid4().hex
        response = self.client.post(
            "/api/v1/assets/upload",
            data={
                "title": "直播回放源视频",
                "product_id": "P1001",
                "source": "unit-test",
                "tags": "直播,回放",
            },
            files={
                "file": (
                    f"{marker}.mp4",
                    mp4_bytes(marker),
                    "video/mp4",
                )
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.asset_ids.add(payload["id"])
        return payload

    def _create_plan(self, source_uri: str, *, end_seconds: float = 4) -> str:
        plan = media_asset_service.create(
            MediaAssetCreate(
                asset_type="video",
                title="清爽防晒卖点片段",
                uri=f"{source_uri}#t=1,{end_seconds:g}",
                product_id="P1001",
                source="live-clip-agent",
                tags=["直播切片", "P1001"],
            )
        )
        self.asset_ids.add(plan.id)
        return plan.id

    def test_executes_plan_and_registers_downloadable_mp4(self) -> None:
        source = self._upload_source()
        plan_id = self._create_plan(source["uri"])

        response = self.client.post(
            f"/api/v1/agents/live-clips/plans/{plan_id}/execute"
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        output = payload["output_asset"]
        self.asset_ids.add(output["id"])
        self.assertTrue(payload["physical_cut_completed"])
        self.assertTrue(payload["human_review_required"])
        self.assertEqual(payload["source_asset_id"], source["id"])
        self.assertEqual(payload["duration_seconds"], 3)
        self.assertEqual(output["source"], "live-clip-agent-ffmpeg")
        self.assertEqual(output["storage_provider"], "local")
        self.assertEqual(output["content_type"], "video/mp4")
        self.assertIn("物理切片", output["tags"])
        self.assertEqual(self.fake_ffmpeg.calls, [(1.0, 4.0)])

        downloaded = self.client.get(
            f"/api/v1/assets/{output['id']}/content"
        )
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, mp4_bytes("clip-1.0-4.0"))

    def test_rejects_clip_outside_source_duration(self) -> None:
        source = self._upload_source()
        plan_id = self._create_plan(source["uri"], end_seconds=25)

        response = self.client.post(
            f"/api/v1/agents/live-clips/plans/{plan_id}/execute"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("超过源视频时长", response.json()["detail"])
        self.assertEqual(self.fake_ffmpeg.calls, [])

    def test_rejects_external_source_without_local_file(self) -> None:
        source = media_asset_service.create(
            MediaAssetCreate(
                asset_type="video",
                title="外部直播回放",
                uri=f"https://example.com/{uuid4().hex}.mp4",
                product_id="P1001",
                source="unit-test",
                tags=["直播"],
            )
        )
        self.asset_ids.add(source.id)
        plan_id = self._create_plan(source.uri)

        response = self.client.post(
            f"/api/v1/agents/live-clips/plans/{plan_id}/execute"
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("没有本地文件", response.json()["detail"])

    def test_returns_404_for_unknown_plan(self) -> None:
        response = self.client.post(
            "/api/v1/agents/live-clips/plans/not-found/execute"
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("切片计划素材不存在", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
