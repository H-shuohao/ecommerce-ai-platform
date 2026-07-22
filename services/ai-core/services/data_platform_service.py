import json
from pathlib import Path

from app.schemas.data_platform import (
    DataAsset,
    DataCatalog,
    DataQualityCheck,
    DataQualityReport,
)
from config import settings
from database import Database, database


COMMERCE_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "commerce.json"


class DataPlatformService:
    def __init__(
        self,
        db: Database = database,
        commerce_data_path: Path = COMMERCE_DATA_PATH,
        commerce_data: dict | None = None,
    ) -> None:
        self.db = db
        self.commerce_data_path = commerce_data_path
        self.commerce_data = commerce_data

    def _load_commerce_data(self) -> dict:
        if self.commerce_data is not None:
            return self.commerce_data
        with self.commerce_data_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def get_catalog(self) -> DataCatalog:
        commerce = self._load_commerce_data()
        with self.db.lock:
            table_rows = self.db.connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
            operational_record_count = sum(
                self.db.connection.execute(
                    f'SELECT COUNT(*) FROM "{row["name"]}"'
                ).fetchone()[0]
                for row in table_rows
            )
        rag_configured = bool(
            settings.VOLC_AK
            and settings.VOLC_SK
            and settings.VOLC_ACCOUNT_ID
            and settings.KB_COLLECTION_NAME
        )
        assets = [
            DataAsset(
                name="commerce.products",
                source_type="json",
                description="电商商品主数据",
                record_count=len(commerce.get("products", [])),
                status="available",
                owner="commerce",
            ),
            DataAsset(
                name="commerce.inventory",
                source_type="json",
                description="商品实时库存演示数据",
                record_count=len(commerce.get("inventory", {})),
                status="available",
                owner="commerce",
            ),
            DataAsset(
                name="commerce.orders",
                source_type="json",
                description="电商订单演示数据",
                record_count=len(commerce.get("orders", [])),
                status="available",
                owner="commerce",
            ),
            DataAsset(
                name="ai_core.operational",
                source_type="sqlite",
                description="Agent运行、会话、内容审核和评测数据",
                record_count=operational_record_count,
                status="available",
                owner="ai-platform",
            ),
            DataAsset(
                name="knowledge_base.commerce",
                source_type="knowledge_base",
                description="火山引擎电商知识库",
                record_count=None,
                status="available" if rag_configured else "not_configured",
                owner="ai-platform",
            ),
        ]
        return DataCatalog(total_assets=len(assets), assets=assets)

    @staticmethod
    def _check(name: str, details: list[str]) -> DataQualityCheck:
        return DataQualityCheck(
            name=name,
            passed=not details,
            issue_count=len(details),
            details=details,
        )

    def check_commerce_quality(self) -> DataQualityReport:
        data = self._load_commerce_data()
        products = data.get("products", [])
        inventory = data.get("inventory", {})
        orders = data.get("orders", [])
        product_ids = [item.get("id") for item in products]
        valid_product_ids = {item for item in product_ids if item}
        order_ids = [item.get("id") for item in orders]

        required_product_fields = {
            "id", "name", "category", "brand", "price", "description", "tags"
        }
        checks = [
            self._check(
                "商品ID唯一性",
                sorted({item for item in product_ids if item and product_ids.count(item) > 1}),
            ),
            self._check(
                "商品必填字段完整性",
                [
                    f"商品索引{index}缺少: {', '.join(sorted(required_product_fields - item.keys()))}"
                    for index, item in enumerate(products)
                    if required_product_fields - item.keys()
                ],
            ),
            self._check(
                "商品价格非负",
                [str(item.get("id")) for item in products if item.get("price", -1) < 0],
            ),
            self._check(
                "商品库存覆盖",
                sorted(valid_product_ids - set(inventory)),
            ),
            self._check(
                "库存引用有效商品",
                sorted(set(inventory) - valid_product_ids),
            ),
            self._check(
                "库存数量非负",
                [product_id for product_id, quantity in inventory.items() if quantity < 0],
            ),
            self._check(
                "订单ID唯一性",
                sorted({item for item in order_ids if item and order_ids.count(item) > 1}),
            ),
            self._check(
                "订单商品引用有效",
                [
                    f"{order.get('id')} -> {product_id}"
                    for order in orders
                    for product_id in order.get("product_ids", [])
                    if product_id not in valid_product_ids
                ],
            ),
        ]
        passed_checks = sum(check.passed for check in checks)
        total_checks = len(checks)
        return DataQualityReport(
            dataset="commerce",
            quality_score=round(passed_checks / total_checks * 100, 2),
            passed_checks=passed_checks,
            failed_checks=total_checks - passed_checks,
            checks=checks,
        )

    def preview_commerce_quality(self, candidate: dict) -> DataQualityReport:
        if not isinstance(candidate.get("products"), list):
            raise ValueError("候选数据的 products 必须是数组")
        if not isinstance(candidate.get("inventory"), dict):
            raise ValueError("候选数据的 inventory 必须是对象")
        if not isinstance(candidate.get("orders"), list):
            raise ValueError("候选数据的 orders 必须是数组")
        preview_service = DataPlatformService(
            db=self.db,
            commerce_data=candidate,
        )
        return preview_service.check_commerce_quality()


data_platform_service = DataPlatformService()
