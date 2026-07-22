from typing import Literal

from pydantic import BaseModel, Field, model_validator


ContentPlatform = Literal["xiaohongshu", "douyin", "wechat"]
ContentTone = Literal["professional", "friendly", "energetic"]


class ContentGenerateRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=50)
    platform: ContentPlatform
    tone: ContentTone = "friendly"


class ContentGenerateResponse(BaseModel):
    draft_id: str | None = None
    product_id: str
    platform: ContentPlatform
    title: str
    body: str
    hashtags: list[str]
    source_facts: dict[str, object]
    human_review_required: bool = True
    status: Literal["pending", "approved", "rejected"] = "pending"


class ContentDraft(ContentGenerateResponse):
    tone: ContentTone
    review_comment: str | None = None
    created_at: str
    updated_at: str


class ContentReviewRequest(BaseModel):
    action: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=500)


class ContentDraftUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    hashtags: list[str] | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if self.title is None and self.body is None and self.hashtags is None:
            raise ValueError("至少需要修改一个字段")
        return self


class ComplianceIssue(BaseModel):
    category: Literal["absolute_claim", "medical_claim", "unverified_promotion"]
    term: str
    message: str
    severity: Literal["medium", "high"]


class ContentComplianceResult(BaseModel):
    draft_id: str
    passed: bool
    risk_level: Literal["low", "medium", "high"]
    issues: list[ComplianceIssue]
