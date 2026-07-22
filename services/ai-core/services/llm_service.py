from collections.abc import Iterator
from typing import Any

from config import settings

try:
    from volcenginesdkarkruntime import Ark
except ImportError:
    Ark = None


SYSTEM_PROMPT = """
# 角色
你是“小懒 AI 项目助手”，帮助一名 AI 应用开发初学者学习技术、推进项目、排查问题和准备求职材料。

# 回答规则
1. 先直接回答问题，再补充必要解释。默认使用 2 到 4 个短句；用户要求详细说明时再展开。
2. 提供了【参考知识库】且内容与问题相关时，优先依据知识库中的已确认事实回答，不要复述整段资料。
3. 没有提供可靠知识库内容时，正常使用你的通用知识回答技术、学习和日常问题，不要机械地说“知识库没有记录”。
4. 涉及用户本人的经历、项目进度、配置和求职信息时，如果知识库没有依据，要明确说不确定，不得自行编造。
5. 操作类问题给出清晰步骤和成功判断标准；概念类问题先用简单语言解释，再结合当前项目举例。
6. 不索要或输出 API Key、Token、Secret、密码等敏感信息。
""".strip()


class LLMService:
    def __init__(self) -> None:
        self.client = None
        if Ark is None:
            print("[LLMService] Ark SDK 未安装，请安装 volcengine-python-sdk[ark]")
            return

        api_key = settings.ARK_API_KEY
        if not api_key:
            print("[LLMService] ARK_API_KEY 未配置，无法调用模型")
            return

        self.client = Ark(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=api_key,
            timeout=60,
        )

    def chat_stream(
        self,
        history_messages: list[dict[str, Any]],
        rag_context: str = "",
    ) -> Iterator[Any]:
        if not self.client:
            yield None
            return

        system_blocks = [SYSTEM_PROMPT]
        if rag_context:
            system_blocks.append(f"### 参考知识库\n{rag_context.strip()}")

        messages = [{"role": "system", "content": "\n\n".join(system_blocks)}]
        messages.extend(history_messages)

        try:
            print(f"[LLMService] 发起流式调用，模型: {settings.ARK_ENDPOINT_ID}")
            stream = self.client.chat.completions.create(
                model=settings.ARK_ENDPOINT_ID,
                messages=messages,
                temperature=0.1,
                top_p=0.5,
                max_tokens=256,
                thinking={"type": "disabled"},
                stream=True,
                stream_options={"include_usage": True},
            )

            for chunk in stream:
                yield chunk
        except Exception as exc:
            print(f"[LLMService] 调用失败: {exc}")
            yield None

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.1,
    ) -> str:
        """Return one complete text response for planning or final synthesis."""
        if not self.client:
            raise RuntimeError("大模型客户端未配置")

        try:
            response = self.client.chat.completions.create(
                model=settings.ARK_ENDPOINT_ID,
                messages=messages,
                temperature=temperature,
                top_p=0.5,
                max_tokens=max_tokens,
                thinking={"type": "disabled"},
                stream=False,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise RuntimeError(f"大模型调用失败: {exc}") from exc


llm_service = LLMService()
