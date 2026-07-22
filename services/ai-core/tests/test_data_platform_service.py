import unittest

from database import Database
from services.data_platform_service import DataPlatformService


class DataPlatformServiceTests(unittest.TestCase):
    def test_detects_invalid_inventory_and_order_reference(self) -> None:
        bad_data = {
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
            "inventory": {"P1": -1, "UNKNOWN": 3},
            "orders": [
                {
                    "id": "O1",
                    "product_ids": ["UNKNOWN"],
                }
            ],
        }
        db = Database(":memory:")
        service = DataPlatformService(db=db, commerce_data=bad_data)

        report = service.check_commerce_quality()

        failed_names = {check.name for check in report.checks if not check.passed}
        self.assertIn("库存数量非负", failed_names)
        self.assertIn("库存引用有效商品", failed_names)
        self.assertIn("订单商品引用有效", failed_names)
        self.assertLess(report.quality_score, 100)
        db.connection.close()


if __name__ == "__main__":
    unittest.main()
