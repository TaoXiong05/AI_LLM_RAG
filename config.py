"""集中管理配置：从 .env 读取 Postgres 连接信息与 LLM/Embedding 配置。"""
import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()

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

    collection_name: str
    top_k: int
    clear_kb_password: str

    @property
    def pg_connection_string(self) -> str:
        user = quote_plus(self.pg_user)
        password = quote_plus(self.pg_password)
        return (
            f"postgresql+psycopg://{user}:{password}@"
            f"{self.pg_host}:{self.pg_port}/{self.pg_database}"
            f"?sslmode={self.pg_sslmode}"
        )


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
        collection_name=os.getenv("COLLECTION_NAME", "rag_default_kb"),
        top_k=int(os.getenv("TOP_K", "3")),
        clear_kb_password=os.getenv("CLEAR_KB_PASSWORD", ""),
    )


settings = get_settings()
