from typing import Literal

from pydantic import BaseModel, Field


class Product(BaseModel):
    id: str
    name: str
    category: str
    brand: str
    price: float = Field(ge=0)
    description: str
    tags: list[str] = Field(default_factory=list)


class ProductListResponse(BaseModel):
    items: list[Product]
    total: int


class InventoryResponse(BaseModel):
    product_id: str
    quantity: int = Field(ge=0)
    in_stock: bool


class Order(BaseModel):
    id: str
    user_id: str
    status: Literal["paid", "shipped", "completed", "cancelled"]
    product_ids: list[str]
    total_amount: float = Field(ge=0)
    tracking_number: str | None = None

