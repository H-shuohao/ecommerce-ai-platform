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
    messages: list[ConversationMessage]
