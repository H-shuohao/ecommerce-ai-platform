from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.jwt_auth import (
    create_access_token,
    hash_password,
    load_users,
    verify_password,
)
from app.core.security import admin_access
from app.schemas.auth import (
    AuthUserResponse,
    CreateAuthUserRequest,
    LoginAuditResponse,
    LoginRequest,
    TokenResponse,
)
from config import settings
from services.auth_user_repository import auth_user_repository


router = APIRouter(prefix="/api/v1/auth", tags=["身份认证"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="用户名密码登录并签发JWT",
)
async def login(request: LoginRequest, http_request: Request) -> TokenResponse:
    if not settings.JWT_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT登录未启用",
        )
    user = auth_user_repository.get_login_user(request.username)
    if user is None:
        try:
            users = load_users(settings.AUTH_USERS_JSON)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="JWT用户配置无效",
            ) from error
        user = users.get(request.username)
    if user is None or not verify_password(request.password, user.password_hash):
        auth_user_repository.record_login(
            username=request.username,
            success=False,
            reason="invalid_credentials",
            client_ip=http_request.client.host if http_request.client else None,
        )
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
    auth_user_repository.record_login(
        username=user.username,
        success=True,
        reason=None,
        client_ip=http_request.client.host if http_request.client else None,
    )
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        role=user.role,
    )


@router.post(
    "/users",
    response_model=AuthUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建数据库登录用户",
    dependencies=[Depends(admin_access)],
)
async def create_auth_user(request: CreateAuthUserRequest) -> AuthUserResponse:
    try:
        return auth_user_repository.create_user(
            username=request.username,
            password_hash=hash_password(request.password),
            role=request.role,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get(
    "/users",
    response_model=list[AuthUserResponse],
    summary="查看数据库登录用户",
    dependencies=[Depends(admin_access)],
)
async def list_auth_users(
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuthUserResponse]:
    return auth_user_repository.list_users(limit=limit)


@router.get(
    "/login-audits",
    response_model=list[LoginAuditResponse],
    summary="查看登录成功与失败审计",
    dependencies=[Depends(admin_access)],
)
async def list_login_audits(
    limit: int = Query(default=100, ge=1, le=500),
) -> list[LoginAuditResponse]:
    return auth_user_repository.list_login_audits(limit=limit)
