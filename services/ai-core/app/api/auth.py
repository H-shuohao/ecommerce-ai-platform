from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.jwt_auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    JwtValidationError,
    load_users,
    verify_password,
)
from app.core.security import Principal, admin_access, authenticate
from app.schemas.auth import (
    AuthUserResponse,
    ChangePasswordRequest,
    CreateAuthUserRequest,
    LoginAuditResponse,
    LoginRequest,
    RefreshTokenRequest,
    SetAuthUserStatusRequest,
    TokenResponse,
)
from config import settings
from services.auth_user_repository import auth_user_repository


router = APIRouter(prefix="/api/v1/auth", tags=["身份认证"])


def _issue_token_pair(user) -> TokenResponse:
    access_token, expires_at = create_access_token(
        username=user.username,
        role=user.role,
        secret=settings.JWT_SECRET,
        issuer=settings.JWT_ISSUER,
        expires_minutes=settings.JWT_EXPIRES_MINUTES,
        token_type="access",
        token_version=user.token_version,
    )
    refresh_token, refresh_expires_at = create_access_token(
        username=user.username,
        role=user.role,
        secret=settings.JWT_SECRET,
        issuer=settings.JWT_ISSUER,
        expires_minutes=settings.JWT_REFRESH_EXPIRES_DAYS * 24 * 60,
        token_type="refresh",
        token_version=user.token_version,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        refresh_expires_at=refresh_expires_at,
        role=user.role,
    )


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
    auth_user_repository.record_login(
        username=user.username,
        success=True,
        reason=None,
        client_ip=http_request.client.host if http_request.client else None,
    )
    return _issue_token_pair(user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="使用Refresh Token换取新Token",
)
async def refresh_token(request: RefreshTokenRequest) -> TokenResponse:
    if not settings.JWT_AUTH_ENABLED or not settings.JWT_SECRET:
        raise HTTPException(status_code=503, detail="JWT登录未启用")
    try:
        payload = decode_access_token(
            request.refresh_token,
            secret=settings.JWT_SECRET,
            issuer=settings.JWT_ISSUER,
            expected_type="refresh",
        )
    except JwtValidationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    user = auth_user_repository.get_login_user(str(payload["sub"]))
    if user is None and payload.get("token_version") is None:
        try:
            user = load_users(settings.AUTH_USERS_JSON).get(str(payload["sub"]))
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail="JWT用户配置无效",
            ) from error
    if (
        user is None
        or payload.get("token_version") != user.token_version
        or payload.get("role") != user.role
    ):
        raise HTTPException(status_code=401, detail="Refresh Token已失效")
    return _issue_token_pair(user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="登录用户修改自己的密码",
)
async def change_password(
    request: ChangePasswordRequest,
    principal: Principal = Depends(authenticate),
) -> None:
    changed = auth_user_repository.change_password(
        username=principal.name,
        current_password=request.current_password,
        new_password_hash=hash_password(request.new_password),
    )
    if not changed:
        raise HTTPException(
            status_code=400,
            detail="当前密码错误，或该账号不是数据库账号",
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


@router.patch(
    "/users/{username}/status",
    response_model=AuthUserResponse,
    summary="管理员停用或启用数据库账号",
    dependencies=[Depends(admin_access)],
)
async def set_auth_user_status(
    username: str,
    request: SetAuthUserStatusRequest,
) -> AuthUserResponse:
    user = auth_user_repository.set_active(
        username=username,
        is_active=request.is_active,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


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
