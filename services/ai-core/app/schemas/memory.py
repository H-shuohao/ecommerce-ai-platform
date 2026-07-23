from typing import Literal

from pydantic import BaseModel


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ConversationSession(BaseModel):
    id: str
    created_at: str
    updated_at: str
    current_product_id: str | None = None
    messages: list[ConversationMessage]
