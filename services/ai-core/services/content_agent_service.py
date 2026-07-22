import asyncio
import json
from typing import Any

from app.schemas.content_agents import ContentGenerateResponse, ContentPlatform, ContentTone
from app.tools.registry import tool_registry
from services.llm_service import llm_service


CONTENT_PROMPT = """
你是电商内容运营 Agent。根据经过业务工具查询的商品事实，生成指定平台的中文营销文案。
只能使用输入中的商品事实，不得编造功效、折扣、销量、库存或用户评价。
输出必须是一个 JSON 对象，不要输出 Markdown 或解释，格式为：
{"title":"标题","body":"正文","hashtags":["标签1","标签2"]}
小红书风格重视真实体验与清晰卖点；抖音风格开头简洁有吸引力；微信公众号风格信息完整、表达专业。
所有内容均为待人工审核草稿，不要使用绝对化、医疗化或保证效果的表达。
""".strip()


class ContentAgentService:
    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("模型没有返回有效 JSON")
        value = json.loads(text[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("内容结果必须是 JSON 对象")
        return value

    async def generate(
        self,
        product_id: str,
        platform: ContentPlatform,
        tone: ContentTone,
    ) -> ContentGenerateResponse:
        product_result = tool_registry.invoke(
            "get_product",
            {"product_id": product_id},
        )
        if not product_result.get("found"):
            raise KeyError(f"商品不存在: {product_id}")
        source_facts = product_result["product"]
        context = {
            "platform": platform,
            "tone": tone,
            "product": source_facts,
        }
        messages = [
            {"role": "system", "content": CONTENT_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        text = await asyncio.to_thread(
            llm_service.complete,
            messages,
            max_tokens=600,
            temperature=0.4,
        )
        content = self._extract_json(text)
        title = content.get("title")
        body = content.get("body")
        hashtags = content.get("hashtags", [])
        if not isinstance(title, str) or not title.strip():
            raise ValueError("模型返回的标题为空")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("模型返回的正文为空")
        if not isinstance(hashtags, list) or not all(
            isinstance(item, str) for item in hashtags
        ):
            raise ValueError("模型返回的标签格式不正确")

        return ContentGenerateResponse(
            product_id=product_id,
            platform=platform,
            title=title.strip(),
            body=body.strip(),
            hashtags=[item.strip().lstrip("#") for item in hashtags[:8] if item.strip()],
            source_facts=source_facts,
            human_review_required=True,
        )


content_agent_service = ContentAgentService()
