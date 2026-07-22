import json

from mcp.server.fastmcp import FastMCP

from app.tools.registry import tool_registry
from services.data_platform_service import data_platform_service


commerce_mcp = FastMCP(
    name="ecommerce-ai-tools",
    instructions=(
        "提供经过参数校验的电商商品、库存和订单查询工具。"
        "库存和订单属于动态业务数据，客户端不得自行编造。"
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    log_level="WARNING",
)


@commerce_mcp.resource("commerce://data-catalog")
def get_data_catalog() -> str:
    """Return the read-only catalog of data assets managed by the data platform."""
    catalog = data_platform_service.get_catalog()
    return json.dumps(catalog.model_dump(), ensure_ascii=False, indent=2)


@commerce_mcp.prompt()
def presales_assistant(customer_question: str) -> str:
    """Build reusable instructions for an e-commerce presales assistant."""
    return f"""你是一名电商售前助手，请回答客户问题：{customer_question}

工作规则：
1. 商品推荐先调用 search_products，不得编造商品。
2. 商品详情调用 get_product。
3. 库存属于动态数据，客户询问库存时必须调用 check_inventory。
4. 订单和物流属于动态数据，必须调用 query_order。
5. 客户需要商品图片、视频或已审核文案时调用 search_media_assets。
6. 工具返回未找到时，应如实说明，不得猜测。
7. 最终回答要简洁，并说明关键信息来自工具查询结果。
"""


@commerce_mcp.tool()
def search_products(
    keyword: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
) -> dict:
    """根据关键词、分类或最高价格搜索商品。"""
    arguments = {
        name: value
        for name, value in {
            "keyword": keyword,
            "category": category,
            "max_price": max_price,
        }.items()
        if value is not None
    }
    return tool_registry.invoke("search_products", arguments)


@commerce_mcp.tool()
def get_product(product_id: str) -> dict:
    """根据商品ID查询商品详情。"""
    return tool_registry.invoke("get_product", {"product_id": product_id})


@commerce_mcp.tool()
def check_inventory(product_id: str) -> dict:
    """根据商品ID查询当前库存。"""
    return tool_registry.invoke("check_inventory", {"product_id": product_id})


@commerce_mcp.tool()
def query_order(order_id: str) -> dict:
    """根据订单ID查询订单和物流状态。"""
    return tool_registry.invoke("query_order", {"order_id": order_id})


@commerce_mcp.tool()
def search_media_assets(
    product_id: str | None = None,
    asset_type: str | None = None,
    tag: str | None = None,
) -> dict:
    """按商品、类型或标签检索素材中心的可用素材。"""
    arguments = {
        name: value
        for name, value in {
            "product_id": product_id,
            "asset_type": asset_type,
            "tag": tag,
        }.items()
        if value is not None
    }
    return tool_registry.invoke("search_media_assets", arguments)
