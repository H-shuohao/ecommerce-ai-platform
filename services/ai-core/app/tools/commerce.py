from typing import Any

from services.commerce_service import commerce_service


def search_products(
    keyword: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
) -> dict[str, Any]:
    products = commerce_service.search_products(
        keyword=keyword,
        category=category,
        max_price=max_price,
    )
    return {
        "items": [product.model_dump() for product in products],
        "total": len(products),
    }


def get_product(product_id: str) -> dict[str, Any]:
    product = commerce_service.get_product(product_id)
    return {
        "found": product is not None,
        "product": product.model_dump() if product else None,
    }


def check_inventory(product_id: str) -> dict[str, Any]:
    inventory = commerce_service.get_inventory(product_id)
    return {
        "found": inventory is not None,
        "inventory": inventory.model_dump() if inventory else None,
    }


def query_order(order_id: str) -> dict[str, Any]:
    order = commerce_service.get_order(order_id)
    return {
        "found": order is not None,
        "order": order.model_dump() if order else None,
    }
