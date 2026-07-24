import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from config import settings


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
access_logger = logging.getLogger("ai_core.access")
error_logger = logging.getLogger("ai_core.error")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_context.get()),
        }
        for field in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client",
            "error_type",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    for logger in (access_logger, error_logger):
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False


def _resolve_request_id(request: Request) -> str:
    candidate = request.headers.get("X-Request-ID", "").strip()
    if candidate and len(candidate) <= 64 and all(
        character.isalnum() or character in "-_." for character in candidate
    ):
        return candidate
    return str(uuid.uuid4())


async def observe_request(request: Request, call_next):
    request_id = _resolve_request_id(request)
    token = request_id_context.set(request_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        access_logger.info(
            "http_request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "client": request.client.host if request.client else None,
            },
        )
        return response
    except Exception as error:
        error_logger.exception(
            "http_request_failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "client": request.client.host if request.client else None,
                "error_type": type(error).__name__,
            },
        )
        raise
    finally:
        request_id_context.reset(token)


def _error_code(status_code: int) -> str:
    return {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "AUTHENTICATION_REQUIRED",
        status.HTTP_403_FORBIDDEN: "PERMISSION_DENIED",
        status.HTTP_404_NOT_FOUND: "RESOURCE_NOT_FOUND",
        status.HTTP_409_CONFLICT: "RESOURCE_CONFLICT",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
        status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_NOT_READY",
    }.get(status_code, "HTTP_ERROR")


def _error_response(
    *,
    status_code: int,
    detail,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    message = detail if isinstance(detail, str) else "请求处理失败"
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            {
                "detail": detail,
                "error": {
                    "code": _error_code(status_code),
                    "message": message,
                    "request_id": request_id_context.get(),
                },
            }
        ),
        headers=headers,
    )


async def http_exception_handler(
    request: Request,
    error: HTTPException,
) -> JSONResponse:
    return _error_response(
        status_code=error.status_code,
        detail=error.detail,
        headers=error.headers,
    )


async def validation_exception_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=error.errors(),
    )


async def unexpected_exception_handler(
    request: Request,
    error: Exception,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="服务器内部错误",
    )
