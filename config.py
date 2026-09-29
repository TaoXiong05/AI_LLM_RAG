"""集中管理配置：从 .env 读取 Postgres 连接信息与 LLM/Embedding 配置。"""
import os
from dataclasses import dataclass
from email.utils import parseaddr
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv(override=True)

try:
    # Streamlit Community Cloud 没有 .env 文件，配置通过它的 Secrets 面板（st.secrets）注入，
    # 这里把它合并进 os.environ，这样下面的 os.getenv 读取方式在本地和云端都能用同一套逻辑。
    import streamlit as st

    for _key, _value in st.secrets.items():
        os.environ.setdefault(_key, str(_value))
except Exception:  # noqa: BLE001 - 本地没有 secrets.toml，或者不在 streamlit 环境里运行，都直接跳过
    pass

# 默认值与 03RAG_Demo.py 保持一致，即使 .env 没填全也能跑起来
DEFAULT_OPENAI_BASE_URL = "https://ws-wibk6xl3op0zm1sx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
DEFAULT_CHAT_MODEL = "qwen3.8-max"
DEFAULT_EMBED_MODEL = "text-embedding-v3"
# OCR 用独立的视觉模型（当前走 Google Gemini OpenAI 兼容接口）
DEFAULT_OCR_MODEL = "gemini-3.5-flash"


@dataclass(frozen=True)
class Settings:
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str
    pg_sslmode: str

    openai_base_url: str
    openai_api_key: str
    chat_model: str
    embed_model: str
    ocr_model: str

    collection_name: str
    top_k: int
    retrieval_max_distance: float
    clear_kb_password: str

    rate_limit_max_requests: int
    rate_limit_window_seconds: float
    rate_limit_ban_seconds: float

    resend_api_key: str
    mail_from: str
    mail_poll_seconds: float
    mail_per_sender_daily_limit: int
    mail_daily_global_limit: int
    mail_max_questions: int
    mail_max_body_chars: int
    mail_max_retries: int
    mail_max_age_hours: float

    @property
    def pg_connection_string(self) -> str:
        user = quote_plus(self.pg_user)
        password = quote_plus(self.pg_password)
        return (
            f"postgresql+psycopg://{user}:{password}@"
            f"{self.pg_host}:{self.pg_port}/{self.pg_database}"
            f"?sslmode={self.pg_sslmode}"
        )

    @property
    def mail_address(self) -> str:
        """MAIL_FROM 中的纯邮箱地址（小写），用于识别收件人和防止自己回复自己。"""
        return parseaddr(self.mail_from)[1].lower()


def get_settings() -> Settings:
    return Settings(
        pg_host=os.getenv("PG_HOST", "localhost"),
        pg_port=int(os.getenv("PG_PORT", "5432")),
        pg_database=os.getenv("PG_DATABASE", "ragdb"),
        pg_user=os.getenv("PG_USER", "postgres"),
        pg_password=os.getenv("PG_PASSWORD", ""),
        pg_sslmode=os.getenv("PG_SSLMODE", "prefer"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        chat_model=os.getenv("CHAT_MODEL", DEFAULT_CHAT_MODEL),
        embed_model=os.getenv("EMBED_MODEL", DEFAULT_EMBED_MODEL),
        ocr_model=os.getenv("OCR_MODEL", DEFAULT_OCR_MODEL),
        collection_name=os.getenv("COLLECTION_NAME", "rag_default_kb"),
        top_k=int(os.getenv("TOP_K", "3")),
        # 检索结果的相关度阈值。pgvector 按余弦距离返回 score（越小越相关，0=完全一致，
        # 1=正交、无相关性）。距离达到该阈值的片段视为低质量检索结果，不再作为引用展示。
        retrieval_max_distance=float(os.getenv("RETRIEVAL_MAX_DISTANCE", "0.8")),
        clear_kb_password=os.getenv("CLEAR_KB_PASSWORD", ""),
        # 每个 IP 在窗口期内允许发起的提问/上传处理次数，超出后封禁该 IP
        rate_limit_max_requests=int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "20")),
        rate_limit_window_seconds=float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", str(60 * 60))),
        rate_limit_ban_seconds=float(os.getenv("RATE_LIMIT_BAN_SECONDS", str(24 * 60 * 60))),
        # 邮件自动回复（Resend 收发信），见 docs/superpowers/specs/2026-09-29-email-auto-reply-design.md
        resend_api_key=os.getenv("RESEND_API_KEY", ""),
        # 用 or 而不是 getenv 默认值：CI 写 .env 时未设置的变量会变成空字符串
        mail_from=os.getenv("MAIL_FROM") or "RAG Support <support@taoxiong.site>",
        mail_poll_seconds=float(os.getenv("MAIL_POLL_SECONDS", "60")),
        mail_per_sender_daily_limit=int(os.getenv("MAIL_PER_SENDER_DAILY_LIMIT", "5")),
        mail_daily_global_limit=int(os.getenv("MAIL_DAILY_GLOBAL_LIMIT", "50")),
        mail_max_questions=int(os.getenv("MAIL_MAX_QUESTIONS", "5")),
        mail_max_body_chars=int(os.getenv("MAIL_MAX_BODY_CHARS", "5000")),
        mail_max_retries=int(os.getenv("MAIL_MAX_RETRIES", "3")),
        mail_max_age_hours=float(os.getenv("MAIL_MAX_AGE_HOURS", "24")),
    )


settings = get_settings()
