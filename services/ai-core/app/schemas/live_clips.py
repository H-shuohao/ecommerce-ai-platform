from pydantic import BaseModel, Field, model_validator


class TranscriptSegment(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("片段结束时间必须大于开始时间")
        return self


class LiveClipPlanRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=50)
    video_uri: str = Field(min_length=1, max_length=2000)
    transcript: list[TranscriptSegment] = Field(min_length=1, max_length=500)
    max_clips: int = Field(default=3, ge=1, le=5)


class LiveClip(BaseModel):
    title: str
    start_seconds: float
    end_seconds: float
    reason: str
    asset_id: str
    clip_uri: str


class LiveClipPlanResponse(BaseModel):
    product_id: str
    source_video_uri: str
    clips: list[LiveClip]
    physical_cut_completed: bool = False
    human_review_required: bool = True
