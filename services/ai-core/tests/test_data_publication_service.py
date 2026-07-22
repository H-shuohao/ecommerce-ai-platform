import unittest

from database import Database
from services.data_platform_service import DataPlatformService
from services.data_publication_service import DataPublicationService
from services.data_release_repository import DataReleaseRepository


GOOD_DATA = {
    "products": [
        {
            "id": "P1",
            "name": "商品",
            "category": "测试",
            "brand": "品牌",
            "price": 10,
            "description": "描述",
            "tags": [],
        }
    ],
    "inventory": {"P1": 3},
    "orders": [],
}


class FakeCommerceService:
    def __init__(self) -> None:
        self.snapshots = []

    def replace_data(self, snapshot: dict) -> None:
        self.snapshots.append(snapshot)


class DataPublicationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Database(":memory:")
        self.repository = DataReleaseRepository(self.db)
        self.commerce = FakeCommerceService()

    def tearDown(self) -> None:
        self.db.connection.close()

    def test_publishes_clean_snapshot(self) -> None:
        platform = DataPlatformService(db=self.db, commerce_data=GOOD_DATA)
        service = DataPublicationService(platform, self.repository, self.commerce)

        release = service.publish_commerce()

        self.assertEqual(release.status, "published")
        self.assertTrue(release.is_active)
        self.assertEqual(release.quality_report.quality_score, 100.0)
        self.assertEqual(self.commerce.snapshots, [GOOD_DATA])

    def test_blocks_dirty_snapshot_without_replacing_agent_data(self) -> None:
        bad_data = {
            **GOOD_DATA,
            "inventory": {"P1": -5},
        }
        platform = DataPlatformService(db=self.db, commerce_data=bad_data)
        service = DataPublicationService(platform, self.repository, self.commerce)

        release = service.publish_commerce()

        self.assertEqual(release.status, "blocked")
        self.assertFalse(release.is_active)
        self.assertEqual(self.commerce.snapshots, [])
        self.assertEqual(self.repository.list()[0].status, "blocked")

    def test_can_rollback_to_previous_published_snapshot(self) -> None:
        first_platform = DataPlatformService(db=self.db, commerce_data=GOOD_DATA)
        first_service = DataPublicationService(
            first_platform,
            self.repository,
            self.commerce,
        )
        first_release = first_service.publish_commerce()
        changed_data = {
            **GOOD_DATA,
            "inventory": {"P1": 9},
        }
        second_service = DataPublicationService(
            DataPlatformService(db=self.db, commerce_data=changed_data),
            self.repository,
            self.commerce,
        )
        second_service.publish_commerce()

        activated = second_service.activate_commerce_release(first_release.id)

        self.assertEqual(activated.id, first_release.id)
        self.assertTrue(activated.is_active)
        self.assertEqual(self.commerce.snapshots[-1], GOOD_DATA)
        releases = self.repository.list()
        active_ids = {release.id for release in releases if release.is_active}
        self.assertEqual(active_ids, {first_release.id})

    def test_blocked_release_cannot_be_activated(self) -> None:
        bad_data = {**GOOD_DATA, "inventory": {"P1": -1}}
        service = DataPublicationService(
            DataPlatformService(db=self.db, commerce_data=bad_data),
            self.repository,
            self.commerce,
        )
        blocked = service.publish_commerce()

        with self.assertRaisesRegex(ValueError, "不能激活"):
            service.activate_commerce_release(blocked.id)


if __name__ == "__main__":
    unittest.main()
