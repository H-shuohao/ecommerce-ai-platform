import time
from typing import Any

from config import settings
from services.token_build import AccessToken, PRIVILEGES


def require_setting(value: Any, name: str) -> Any:
    """Return a required setting or fail with a readable message."""
    if not value:
        raise ValueError(f"缺少环境变量: {name}")
    return value


def build_rtc_token(room_id: str, user_id: str) -> str:
    """Use a configured token or build a temporary RTC room token."""
    if settings.RTC_TOKEN:
        return settings.RTC_TOKEN

    app_id = require_setting(settings.RTC_APP_ID, "RTC_APP_ID")
    app_key = require_setting(settings.RTC_APP_KEY, "RTC_APP_KEY")
    token_builder = AccessToken(app_id, app_key, room_id, user_id)
    token_builder.add_privilege(PRIVILEGES["PrivSubscribeStream"], 0)
    token_builder.add_privilege(PRIVILEGES["PrivPublishStream"], 0)
    token_builder.expire_time(int(time.time()) + 3600 * 24)
    return token_builder.serialize()

