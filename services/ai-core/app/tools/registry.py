from dataclasses import dataclass
from typing import Any, Callable

from app.schemas.tools import ToolDefinitionResponse, ToolParameter
from app.tools.commerce import (
    check_inventory,
    get_product,
    query_order,
    search_products,
)
from app.tools.media_assets import search_media_assets


ToolHandler = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: list[ToolParameter]
    handler: ToolHandler

    def public_definition(self) -> ToolDefinitionResponse:
        return ToolDefinitionResponse(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"工具已经注册: {definition.name}")
        self._tools[definition.name] = definition

    def list_tools(self) -> list[ToolDefinitionResponse]:
        return [tool.public_definition() for tool in self._tools.values()]

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        definition = self._tools.get(name)
        if definition is None:
            raise KeyError(f"未知工具: {name}")

        allowed = {parameter.name for parameter in definition.parameters}
        required = {
            parameter.name
            for parameter in definition.parameters
            if parameter.required
        }
        missing = sorted(required - arguments.keys())
        unknown = sorted(arguments.keys() - allowed)
        if missing:
            raise ValueError(f"缺少必填参数: {', '.join(missing)}")
        if unknown:
            raise ValueError(f"包含未知参数: {', '.join(unknown)}")

        return definition.handler(**arguments)


tool_registry = ToolRegistry()
tool_registry.register(
    ToolDefinition(
        name="search_products",
        description="根据关键词或分类搜索商品",
        parameters=[
            ToolParameter(name="keyword", type="string", required=False, description="商品关键词"),
            ToolParameter(name="category", type="string", required=False, description="商品分类"),
            ToolParameter(name="max_price", type="number", required=False, description="用户可接受的最高价格"),
        ],
        handler=search_products,
    )
)
tool_registry.register(
    ToolDefinition(
        name="get_product",
        description="根据商品 ID 查询商品详情",
        parameters=[
            ToolParameter(name="product_id", type="string", required=True, description="商品 ID")
        ],
        handler=get_product,
    )
)
tool_registry.register(
    ToolDefinition(
        name="check_inventory",
        description="根据商品 ID 查询实时库存",
        parameters=[
            ToolParameter(name="product_id", type="string", required=True, description="商品 ID")
        ],
        handler=check_inventory,
    )
)
tool_registry.register(
    ToolDefinition(
        name="query_order",
        description="根据订单 ID 查询订单和物流状态",
        parameters=[
            ToolParameter(name="order_id", type="string", required=True, description="订单 ID")
        ],
        handler=query_order,
    )
)
tool_registry.register(
    ToolDefinition(
        name="search_media_assets",
        description="按商品ID、素材类型或标签检索已登记的图片、视频和文本素材",
        parameters=[
            ToolParameter(name="product_id", type="string", required=False, description="关联商品ID"),
            ToolParameter(name="asset_type", type="string", required=False, description="image、video或text"),
            ToolParameter(name="tag", type="string", required=False, description="素材标签"),
        ],
        handler=search_media_assets,
    )
)
