from fastapi import APIRouter, HTTPException, status

from app.core.jwt_auth import create_access_token, load_users, verify_password
from app.schemas.auth import LoginRequest, TokenResponse
from config import settings


router = APIRouter(prefix="/api/v1/auth", tags=["身份认证"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="用户名密码登录并签发JWT",
)
async def login(request: LoginRequest) -> TokenResponse:
    if not settings.JWT_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT登录未启用",
        )
    try:
        users = load_users(settings.AUTH_USERS_JSON)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT用户配置无效",
        ) from error
    user = users.get(request.username)
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not settings.JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT签名密钥未配置",
        )
    token, expires_at = create_access_token(
        username=user.username,
        role=user.role,
        secret=settings.JWT_SECRET,
        issuer=settings.JWT_ISSUER,
        expires_minutes=settings.JWT_EXPIRES_MINUTES,
    )
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        role=user.role,
    )
