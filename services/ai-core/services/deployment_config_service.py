from dataclasses import dataclass
from typing import Mapping


TRUE_VALUES = {"1", "true", "yes", "on"}
MIN_API_KEY_LENGTH = 16


@dataclass(frozen=True)
class DeploymentCheckResult:
    passed: bool
    errors: list[str]
    warnings: list[str]


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUE_VALUES


def _missing(environment: Mapping[str, str], names: tuple[str, ...]) -> list[str]:
    return [name for name in names if not environment.get(name, "").strip()]


def validate_deployment_config(
    environment: Mapping[str, str],
    *,
    production: bool,
) -> DeploymentCheckResult:
    errors: list[str] = []
    warnings: list[str] = []

    llm_missing = _missing(environment, ("ARK_API_KEY", "ARK_ENDPOINT_ID"))
    if llm_missing:
        errors.append("大模型配置缺失: " + ", ".join(llm_missing))

    rag_missing = _missing(
        environment,
        (
            "VOLC_ACCESS_KEY",
            "VOLC_SECRET_KEY",
            "VOLC_ACCOUNT_ID",
            "KB_COLLECTION_NAME",
        ),
    )
    if rag_missing:
        errors.append("RAG配置缺失: " + ", ".join(rag_missing))

    auth_enabled = _enabled(environment.get("API_AUTH_ENABLED"))
    if production and not auth_enabled:
        errors.append("生产模式必须设置 API_AUTH_ENABLED=true")

    if auth_enabled:
        key_names = ("API_VIEWER_KEY", "API_SERVICE_KEY", "API_ADMIN_KEY")
        missing_keys = _missing(environment, key_names)
        if missing_keys:
            errors.append("API认证密钥缺失: " + ", ".join(missing_keys))
        else:
            key_values = [environment[name].strip() for name in key_names]
            weak_keys = [
                name
                for name, value in zip(key_names, key_values, strict=True)
                if len(value) < MIN_API_KEY_LENGTH
            ]
            if weak_keys:
                errors.append(
                    f"API认证密钥至少需要{MIN_API_KEY_LENGTH}位: "
                    + ", ".join(weak_keys)
                )
            if len(set(key_values)) != len(key_values):
                errors.append("viewer、service、admin 必须使用不同的 API Key")
    else:
        warnings.append("API认证未启用，仅适合本地开发演示")

    jwt_enabled = _enabled(environment.get("JWT_AUTH_ENABLED"))
    if jwt_enabled:
        jwt_secret = environment.get("JWT_SECRET", "").strip()
        if len(jwt_secret) < 32:
            errors.append("JWT_SECRET 至少需要32位")
        users_json = environment.get("AUTH_USERS_JSON", "").strip()
        if not users_json or users_json == "[]":
            warnings.append(
                "JWT登录已启用且未配置环境变量启动账号，请确认数据库已有用户，"
                "或使用admin API Key创建首个用户"
            )
    else:
        warnings.append("JWT登录未启用，仅保留API Key机器认证")

    server_url = environment.get("SERVER_URL", "").strip()
    if server_url and production and not server_url.startswith("https://"):
        errors.append("生产环境 SERVER_URL 必须使用 https://")
    if not server_url:
        warnings.append("未配置 SERVER_URL，RTC 公网回调不可用")

    asr_provider = environment.get("ASR_PROVIDER", "disabled").strip().lower()
    if asr_provider == "openai-compatible":
        asr_missing = _missing(environment, ("ASR_API_URL", "ASR_API_KEY"))
        if asr_missing:
            errors.append("批量ASR配置缺失: " + ", ".join(asr_missing))
    elif asr_provider == "disabled":
        warnings.append("批量ASR未启用，直播切片任务需要手工提供转写")
    else:
        errors.append(f"不支持的ASR_PROVIDER: {asr_provider}")

    rate_limit_enabled = _enabled(environment.get("RATE_LIMIT_ENABLED"))
    if production and not rate_limit_enabled:
        errors.append("生产模式必须设置 RATE_LIMIT_ENABLED=true")
    elif not rate_limit_enabled:
        warnings.append("接口限流未启用，仅适合本地开发演示")

    return DeploymentCheckResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
    )
