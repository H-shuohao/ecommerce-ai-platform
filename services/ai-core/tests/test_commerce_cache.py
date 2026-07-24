import unittest

from fastapi.testclient import TestClient

from main import app
from services.commerce_service import commerce_service


class CommerceCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        commerce_service.clear_product_cache()

    def test_product_search_exposes_cache_hit_and_miss(self) -> None:
        first = self.client.get(
            "/api/v1/products",
            params={"keyword": "油皮"},
        )
        second = self.client.get(
            "/api/v1/products",
            params={"keyword": "油皮"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers["X-Cache"], "MISS")
        self.assertEqual(second.headers["X-Cache"], "HIT")
        self.assertEqual(first.json(), second.json())

    def test_admin_can_inspect_and_clear_cache(self) -> None:
        self.client.get("/api/v1/products", params={"keyword": "防晒"})

        stats = self.client.get("/api/v1/data-platform/cache/commerce")
        cleared = self.client.delete("/api/v1/data-platform/cache/commerce")

        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["size"], 1)
        self.assertGreaterEqual(stats.json()["misses"], 1)
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["cleared_entries"], 1)

    def test_replacing_published_snapshot_invalidates_cache(self) -> None:
        commerce_service.search_products(keyword="油皮")
        self.assertEqual(commerce_service.get_product_cache_stats().size, 1)
        snapshot = {
            "products": [
                product.model_dump()
                for product in commerce_service.products.values()
            ],
            "inventory": dict(commerce_service.inventory),
            "orders": [
                order.model_dump()
                for order in commerce_service.orders.values()
            ],
        }

        commerce_service.replace_data(snapshot)

        self.assertEqual(commerce_service.get_product_cache_stats().size, 0)

    def test_inventory_is_always_read_from_current_snapshot(self) -> None:
        original_quantity = commerce_service.inventory["P1001"]
        try:
            commerce_service.inventory["P1001"] = 36
            first = commerce_service.get_inventory("P1001")
            commerce_service.inventory["P1001"] = 35
            second = commerce_service.get_inventory("P1001")
        finally:
            commerce_service.inventory["P1001"] = original_quantity

        self.assertEqual(first.quantity, 36)
        self.assertEqual(second.quantity, 35)
