from typing import Literal

from pydantic import BaseModel


class DataAsset(BaseModel):
    name: str
    source_type: Literal["json", "sqlite", "knowledge_base"]
    description: str
    record_count: int | None = None
    status: Literal["available", "not_configured"]
    owner: str


class DataCatalog(BaseModel):
    total_assets: int
    assets: list[DataAsset]


class DataQualityCheck(BaseModel):
    name: str
    passed: bool
    issue_count: int
    details: list[str]


class DataQualityReport(BaseModel):
    dataset: str
    quality_score: float
    passed_checks: int
    failed_checks: int
    checks: list[DataQualityCheck]


class DataRelease(BaseModel):
    id: str
    dataset: str
    version_hash: str
    quality_score: float
    status: Literal["published", "blocked"]
    is_active: bool
    created_at: str
    quality_report: DataQualityReport | None = None


class CommerceStagingRequest(BaseModel):
    data: dict


class StagingValidationResponse(BaseModel):
    ready_to_publish: bool
    persisted: bool = False
    quality_report: DataQualityReport
