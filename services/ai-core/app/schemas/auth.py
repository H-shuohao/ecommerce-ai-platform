from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: int
    refresh_expires_at: int
    role: Literal["viewer", "service", "admin"]


class CreateAuthUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["viewer", "service", "admin"]


class AuthUserResponse(BaseModel):
    username: str
    role: Literal["viewer", "service", "admin"]
    is_active: bool
    created_at: str
    updated_at: str


class LoginAuditResponse(BaseModel):
    id: int
    username: str
    success: bool
    reason: str | None
    client_ip: str | None
    created_at: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class SetAuthUserStatusRequest(BaseModel):
    is_active: bool
