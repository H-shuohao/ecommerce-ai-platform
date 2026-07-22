from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(
        description="消息角色，只能是 user 或 assistant",
        examples=["user"],
    )
    content: str = Field(
        min_length=1,
        description="消息正文",
        examples=["我的当前学习阶段是什么？"],
    )


class DebugRequest(BaseModel):
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="可选的历史消息。第一次调试保持空数组即可。",
    )
    question: str = Field(
        min_length=1,
        description="本轮需要检索知识库并交给大模型回答的问题",
        examples=["我的当前学习阶段是什么？"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"history": [], "question": "我的当前学习阶段是什么？"},
                {
                    "history": [
                        {"role": "user", "content": "你是谁？"},
                        {
                            "role": "assistant",
                            "content": "我是小懒 AI 项目助手。",
                        },
                    ],
                    "question": "你能怎样帮助我推进项目？",
                },
            ]
        }
    }


class RagDebugResponse(BaseModel):
    query: str
    retrieved_context: str
    length: int
    score: float | None = None
    relevant: bool
    reason: str
    status: Literal["success", "irrelevant", "no_results_or_error"]


class DebugTiming(BaseModel):
    rag_seconds: float
    first_token_seconds: float | None
    llm_seconds: float
    total_seconds: float


class DebugTokenUsage(BaseModel):
    total_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class DebugChatResponse(BaseModel):
    question: str
    answer: str
    retrieved_context: str
    retrieved_context_length: int
    timing: DebugTiming
    usage: DebugTokenUsage

