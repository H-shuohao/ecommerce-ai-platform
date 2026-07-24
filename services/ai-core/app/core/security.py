import secrets
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from config import settings


class Role(StrEnum):
    VIEWER = "viewer"
    SERVICE = "service"
    ADMIN = "admin"


@dataclass(frozen=True)
class Principal:
    name: str
    role: Role


api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApiKeyAuth",
    description="部署环境启用认证后，在此填写 viewer、service 或 admin API Key。",
    auto_error=False,
)


def _configured_principals() -> tuple[tuple[str, Role, str | None], ...]:
    return (
        ("viewer-client", Role.VIEWER, settings.API_VIEWER_KEY),
        ("service-client", Role.SERVICE, settings.API_SERVICE_KEY),
        ("admin-client", Role.ADMIN, settings.API_ADMIN_KEY),
    )


def resolve_principal(api_key: str | None) -> Principal:
    if not settings.API_AUTH_ENABLED:
        return Principal(name="local-development", role=Role.ADMIN)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    for name, role, configured_key in _configured_principals():
        if configured_key and secrets.compare_digest(api_key, configured_key):
            return Principal(name=name, role=role)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API Key 无效",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def authenticate(api_key: str | None = Depends(api_key_header)) -> Principal:
    return resolve_principal(api_key)


def require_roles(*allowed_roles: Role):
    allowed = frozenset(allowed_roles)

    def authorize(principal: Principal = Depends(authenticate)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前身份没有访问该接口的权限",
            )
        return principal

    return authorize


viewer_access = require_roles(Role.VIEWER, Role.SERVICE, Role.ADMIN)
service_access = require_roles(Role.SERVICE, Role.ADMIN)
admin_access = require_roles(Role.ADMIN)
