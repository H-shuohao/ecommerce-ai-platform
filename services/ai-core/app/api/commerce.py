from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas.commerce import InventoryResponse, Order, Product, ProductListResponse
from services.commerce_service import commerce_service


router = APIRouter(prefix="/api/v1", tags=["电商数据"])


@router.get("/products", response_model=ProductListResponse, summary="搜索商品")
async def search_products(
    response: Response,
    keyword: str | None = Query(default=None, description="名称、品牌、描述或标签"),
    category: str | None = Query(default=None, description="精确匹配商品分类"),
    max_price: float | None = Query(default=None, ge=0, description="最高价格"),
) -> ProductListResponse:
    items, cache_hit = commerce_service.search_products_with_cache(
        keyword=keyword,
        category=category,
        max_price=max_price,
    )
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    return ProductListResponse(items=items, total=len(items))


@router.get("/products/{product_id}", response_model=Product, summary="查询商品详情")
async def get_product(product_id: str) -> Product:
    product = commerce_service.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product


@router.get(
    "/products/{product_id}/inventory",
    response_model=InventoryResponse,
    summary="查询商品库存",
)
async def get_inventory(product_id: str) -> InventoryResponse:
    inventory = commerce_service.get_inventory(product_id)
    if inventory is None:
        raise HTTPException(status_code=404, detail="商品不存在")
    return inventory


@router.get("/orders/{order_id}", response_model=Order, summary="查询订单")
async def get_order(order_id: str) -> Order:
    order = commerce_service.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order
