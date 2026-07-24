import json
from pathlib import Path

from app.schemas.commerce import InventoryResponse, Order, Product
from config import settings
from database import database
from services.cache_service import TTLCache


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "commerce.json"


class CommerceService:
    def __init__(
        self,
        data_file: Path = DATA_FILE,
        product_search_cache: TTLCache | None = None,
    ) -> None:
        self.product_search_cache = product_search_cache or TTLCache(
            ttl_seconds=settings.CACHE_TTL_SECONDS,
            max_entries=settings.CACHE_MAX_ENTRIES,
        )
        with data_file.open("r", encoding="utf-8") as file:
            raw_data = json.load(file)

        with database.lock:
            active_release = database.connection.execute(
                """
                SELECT snapshot_json FROM data_releases
                WHERE dataset = 'commerce' AND status = 'published' AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        if active_release is not None:
            raw_data = json.loads(active_release["snapshot_json"])

        self.replace_data(raw_data)

    def replace_data(self, raw_data: dict) -> None:
        """Atomically replace the in-memory business snapshot after publication."""
        products = {
            item["id"]: Product.model_validate(item)
            for item in raw_data["products"]
        }
        inventory = {
            product_id: int(quantity)
            for product_id, quantity in raw_data["inventory"].items()
        }
        orders = {
            item["id"]: Order.model_validate(item)
            for item in raw_data["orders"]
        }

        self.products = products
        self.inventory = inventory
        self.orders = orders
        self.product_search_cache.clear()

    def search_products(
        self,
        keyword: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
    ) -> list[Product]:
        products, _ = self.search_products_with_cache(
            keyword=keyword,
            category=category,
            max_price=max_price,
        )
        return products

    def search_products_with_cache(
        self,
        keyword: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
    ) -> tuple[list[Product], bool]:
        cache_key = (
            keyword.strip().casefold() if keyword else None,
            category.strip().casefold() if category else None,
            max_price,
        )

        cached_products, cache_hit = self.product_search_cache.get_or_set(
            cache_key,
            lambda: tuple(
                self._filter_products(
                    keyword=keyword,
                    category=category,
                    max_price=max_price,
                )
            ),
        )
        return list(cached_products), cache_hit

    def _filter_products(
        self,
        keyword: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
    ) -> list[Product]:
        products = list(self.products.values())

        if keyword:
            normalized = keyword.casefold()
            matched_products = []
            for product in products:
                fields = [
                    product.name,
                    product.brand,
                    product.description,
                    product.category,
                    *product.tags,
                ]
                searchable = " ".join(fields).casefold()
                short_terms = [
                    value.casefold()
                    for value in [product.name, product.brand, product.category, *product.tags]
                    if len(value.strip()) >= 2
                ]
                if normalized in searchable or any(
                    term in normalized for term in short_terms
                ):
                    matched_products.append(product)
            products = matched_products

        if category:
            products = [
                product
                for product in products
                if product.category.casefold() == category.casefold()
            ]

        if max_price is not None:
            products = [product for product in products if product.price <= max_price]

        return products

    def clear_product_cache(self) -> int:
        return self.product_search_cache.clear()

    def get_product_cache_stats(self):
        return self.product_search_cache.stats()

    def get_product(self, product_id: str) -> Product | None:
        return self.products.get(product_id)

    def get_inventory(self, product_id: str) -> InventoryResponse | None:
        if product_id not in self.products:
            return None
        quantity = self.inventory.get(product_id, 0)
        return InventoryResponse(
            product_id=product_id,
            quantity=quantity,
            in_stock=quantity > 0,
        )

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)


commerce_service = CommerceService()
