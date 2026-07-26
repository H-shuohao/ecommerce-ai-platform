import secrets
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.jwt_auth import JwtValidationError, decode_access_token
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
bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description="网页登录后填写JWT access_token。",
    auto_error=False,
)


def _configured_principals() -> tuple[tuple[str, Role, str | None], ...]:
    return (
        ("viewer-client", Role.VIEWER, settings.API_VIEWER_KEY),
        ("service-client", Role.SERVICE, settings.API_SERVICE_KEY),
        ("admin-client", Role.ADMIN, settings.API_ADMIN_KEY),
    )


def resolve_principal(
    api_key: str | None,
    bearer_token: str | None = None,
) -> Principal:
    if not settings.API_AUTH_ENABLED:
        return Principal(name="local-development", role=Role.ADMIN)

    if bearer_token:
        if not settings.JWT_AUTH_ENABLED or not settings.JWT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT认证未配置",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            payload = decode_access_token(
                bearer_token,
                secret=settings.JWT_SECRET,
                issuer=settings.JWT_ISSUER,
            )
        except JwtValidationError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(error),
                headers={"WWW-Authenticate": "Bearer"},
            ) from error
        return Principal(
            name=str(payload["sub"]),
            role=Role(str(payload["role"])),
        )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 API Key 或 Bearer Token",
            headers={"WWW-Authenticate": "ApiKey, Bearer"},
        )

    for name, role, configured_key in _configured_principals():
        if configured_key and secrets.compare_digest(api_key, configured_key):
            return Principal(name=name, role=role)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API Key 无效",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def authenticate(
    api_key: str | None = Depends(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    token = bearer.credentials if bearer is not None else None
    return resolve_principal(api_key, token)


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
