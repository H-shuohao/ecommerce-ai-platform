import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    API_AUTH_ENABLED = os.getenv("API_AUTH_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    API_VIEWER_KEY = os.getenv("API_VIEWER_KEY")
    API_SERVICE_KEY = os.getenv("API_SERVICE_KEY")
    API_ADMIN_KEY = os.getenv("API_ADMIN_KEY")

    VOLC_AK = os.getenv("VOLC_ACCESS_KEY")
    VOLC_SK = os.getenv("VOLC_SECRET_KEY")
    ARK_ENDPOINT_ID = os.getenv("ARK_ENDPOINT_ID")
    ARK_API_KEY = os.getenv("ARK_API_KEY")

    RTC_APP_ID = os.getenv("RTC_APP_ID")
    RTC_APP_KEY = os.getenv("RTC_APP_KEY")
    RTC_ROOM_ID = os.getenv("RTC_ROOM_ID", "ChatRoom01")
    RTC_USER_ID = os.getenv("RTC_USER_ID", "Huoshan01")
    RTC_TOKEN = os.getenv("RTC_TOKEN")

    VOICE_CHAT_TASK_ID = os.getenv("VOICE_CHAT_TASK_ID", "ChatTask01")
    AGENT_USER_ID = os.getenv("AGENT_USER_ID", "ChatBot01")
    AGENT_WELCOME_MESSAGE = os.getenv(
        "AGENT_WELCOME_MESSAGE",
        "你好，我是小懒，有什么需要帮忙的吗？",
    )

    ASR_APP_ID = os.getenv("ASR_APP_ID")
    TTS_APP_ID = os.getenv("TTS_APP_ID")
    
    SERVER_URL = os.getenv("SERVER_URL")

    KB_COLLECTION_NAME = os.getenv("KB_COLLECTION_NAME", "dw_ai")
    KB_PROJECT_NAME = os.getenv("KB_PROJECT_NAME", "default")
    VOLC_ACCOUNT_ID = os.getenv("VOLC_ACCOUNT_ID")
    KB_MIN_RELEVANCE_SCORE = float(os.getenv("KB_MIN_RELEVANCE_SCORE", "0.22"))
    KB_MAX_CONTEXT_CHARS = int(os.getenv("KB_MAX_CONTEXT_CHARS", "500"))

settings = Config()
