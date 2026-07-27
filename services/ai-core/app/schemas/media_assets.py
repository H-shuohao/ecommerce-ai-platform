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
    storage_provider: Literal["external", "local"] = "external"
    original_filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=100)
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


class MediaAsset(BaseModel):
    id: str
    asset_type: AssetType
    title: str
    uri: str
    product_id: str | None
    source: str
    tags: list[str]
    storage_provider: Literal["external", "local"]
    original_filename: str | None
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    status: AssetStatus
    created_at: str
    updated_at: str


class MediaAssetListResponse(BaseModel):
    items: list[MediaAsset]
    total: int
