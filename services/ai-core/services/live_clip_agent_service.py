import asyncio
import json

from app.schemas.live_clips import LiveClip, LiveClipPlanRequest, LiveClipPlanResponse
from app.schemas.media_assets import MediaAssetCreate
from services.commerce_service import commerce_service
from services.llm_service import llm_service
from services.media_asset_service import media_asset_service


LIVE_CLIP_PROMPT = """
你是电商直播高光切片规划 Agent。根据带时间戳的转写文本选择最值得复用的商品介绍片段。
只能使用输入中的时间范围和文字，不得编造主播没有说过的内容。
返回 JSON 对象，不要输出 Markdown：
{"clips":[{"title":"标题","start_seconds":0,"end_seconds":10,"reason":"入选原因"}]}
每个片段必须满足开始时间小于结束时间，并落在整段转写范围内。优先选择卖点完整、表达清楚的连续片段。
""".strip()


class LiveClipAgentService:
    @staticmethod
    def _extract_json(text: str) -> dict:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("模型没有返回有效 JSON")
        value = json.loads(text[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("切片规划必须是 JSON 对象")
        return value

    async def plan(self, request: LiveClipPlanRequest) -> LiveClipPlanResponse:
        if commerce_service.get_product(request.product_id) is None:
            raise KeyError(f"商品不存在: {request.product_id}")
        transcript_start = min(item.start_seconds for item in request.transcript)
        transcript_end = max(item.end_seconds for item in request.transcript)
        context = {
            "product_id": request.product_id,
            "max_clips": request.max_clips,
            "transcript": [item.model_dump() for item in request.transcript],
        }
        text = await asyncio.to_thread(
            llm_service.complete,
            [
                {"role": "system", "content": LIVE_CLIP_PROMPT},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            max_tokens=800,
            temperature=0.1,
        )
        raw_clips = self._extract_json(text).get("clips")
        if not isinstance(raw_clips, list):
            raise ValueError("模型返回的 clips 格式不正确")

        clips: list[LiveClip] = []
        for raw in raw_clips[: request.max_clips]:
            if not isinstance(raw, dict):
                raise ValueError("切片条目格式不正确")
            title = raw.get("title")
            reason = raw.get("reason")
            start = raw.get("start_seconds")
            end = raw.get("end_seconds")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("切片标题为空")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("切片原因为空")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                raise ValueError("切片时间必须是数字")
            if start < transcript_start or end > transcript_end or end <= start:
                raise ValueError("模型返回的切片时间超出转写范围")
            clip_uri = f"{request.video_uri}#t={float(start):g},{float(end):g}"
            asset = media_asset_service.create(
                MediaAssetCreate(
                    asset_type="video",
                    title=title.strip(),
                    uri=clip_uri,
                    product_id=request.product_id,
                    source="live-clip-agent",
                    tags=["直播切片", request.product_id],
                )
            )
            clips.append(
                LiveClip(
                    title=title.strip(),
                    start_seconds=float(start),
                    end_seconds=float(end),
                    reason=reason.strip(),
                    asset_id=asset.id,
                    clip_uri=clip_uri,
                )
            )
        if not clips:
            raise ValueError("模型没有选择有效切片")
        return LiveClipPlanResponse(
            product_id=request.product_id,
            source_video_uri=request.video_uri,
            clips=clips,
        )


live_clip_agent_service = LiveClipAgentService()
