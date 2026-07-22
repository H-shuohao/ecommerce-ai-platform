from typing import Literal

from pydantic import BaseModel, Field


AssetType = Literal["image", "video", "text"]
AssetStatus = Literal["active", "archived"]


class MediaAssetCreate(BaseModel):
    asset_type: AssetType
    title: str = Field(min_length=1, max_length=200)
    uri: str = Field(min_length=1, max_length=2000)
    product_id: str | None = Field(default=None, min_length=1, max_length=50)
    source: str = Field(default="manual", min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=20)


class MediaAsset(BaseModel):
    id: str
    asset_type: AssetType
    title: str
    uri: str
    product_id: str | None
    source: str
    tags: list[str]
    status: AssetStatus
    created_at: str
    updated_at: str


class MediaAssetListResponse(BaseModel):
    items: list[MediaAsset]
    total: int
