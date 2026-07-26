import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JwtUser:
    username: str
    password_hash: str
    role: str


class JwtValidationError(ValueError):
    pass


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(
    password: str,
    *,
    iterations: int = 310_000,
    salt: bytes | None = None,
) -> str:
    if not password:
        raise ValueError("密码不能为空")
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        actual_salt,
        iterations,
    )
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{_base64url_encode(actual_salt)}${_base64url_encode(digest)}"
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_text = encoded_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = _base64url_decode(salt_text)
        expected = _base64url_decode(expected_text)
    except (TypeError, ValueError, binascii.Error):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def load_users(raw_json: str | None) -> dict[str, JwtUser]:
    if not raw_json or not raw_json.strip():
        return {}
    try:
        records = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise ValueError("AUTH_USERS_JSON 不是合法 JSON") from error
    if not isinstance(records, list):
        raise ValueError("AUTH_USERS_JSON 必须是用户数组")
    users: dict[str, JwtUser] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("AUTH_USERS_JSON 中的用户必须是对象")
        user = JwtUser(
            username=str(record.get("username", "")).strip(),
            password_hash=str(record.get("password_hash", "")).strip(),
            role=str(record.get("role", "")).strip(),
        )
        if not user.username or not user.password_hash or user.role not in {
            "viewer",
            "service",
            "admin",
        }:
            raise ValueError("JWT用户必须包含用户名、密码哈希和合法角色")
        if user.username in users:
            raise ValueError(f"JWT用户名重复: {user.username}")
        users[user.username] = user
    return users


def create_access_token(
    *,
    username: str,
    role: str,
    secret: str,
    issuer: str,
    expires_minutes: int,
    now: int | None = None,
) -> tuple[str, int]:
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + expires_minutes * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "role": role,
        "iss": issuer,
        "iat": issued_at,
        "exp": expires_at,
    }
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(signature)}", expires_at


def decode_access_token(
    token: str,
    *,
    secret: str,
    issuer: str,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        header = json.loads(_base64url_decode(encoded_header))
        payload = json.loads(_base64url_decode(encoded_payload))
        signature = _base64url_decode(encoded_signature)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as error:
        raise JwtValidationError("JWT格式无效") from error
    if header != {"alg": "HS256", "typ": "JWT"} or not isinstance(payload, dict):
        raise JwtValidationError("JWT算法或载荷无效")
    signing_input = f"{encoded_header}.{encoded_payload}"
    expected = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(signature, expected):
        raise JwtValidationError("JWT签名无效")
    current_time = int(time.time()) if now is None else now
    if payload.get("iss") != issuer:
        raise JwtValidationError("JWT签发方无效")
    if not isinstance(payload.get("exp"), int) or payload["exp"] <= current_time:
        raise JwtValidationError("JWT已过期")
    if not payload.get("sub") or payload.get("role") not in {
        "viewer",
        "service",
        "admin",
    }:
        raise JwtValidationError("JWT身份或角色无效")
    return payload
