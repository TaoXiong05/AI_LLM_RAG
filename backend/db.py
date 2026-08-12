"""Postgres / pgvector 相关的所有数据库操作。"""
from functools import lru_cache

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from sqlalchemy import Engine, create_engine, text

from config import settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(settings.pg_connection_string)


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embed_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        # 很多 OpenAI 兼容的第三方端点（包括阿里云百炼）只接受纯文本输入，
        # 关闭这个开关避免 OpenAIEmbeddings 用 tiktoken 预分词后发送 token-id 数组导致 400。
        check_embedding_ctx_length=False,
        # 阿里云百炼 text-embedding-v3 单次请求最多接受 10 条文本，
        # 默认的 chunk_size=1000 会把一整批 chunk 一次性发过去导致 400（batch size is invalid）。
        chunk_size=10,
    )


def ensure_pgvector_extension() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


@lru_cache(maxsize=1)
def get_vector_store() -> PGVector:
    return PGVector(
        embeddings=get_embeddings(),
        collection_name=settings.collection_name,
        connection=settings.pg_connection_string,
        use_jsonb=True,
    )


def test_connection() -> tuple[bool, str]:
    try:
        with get_engine().connect():
            pass
        return True, ""
    except Exception as exc:  # noqa: BLE001 - 需要把任意连接错误转成用户可读的信息
        return False, str(exc)


def add_documents(chunks: list[Document]) -> int:
    if not chunks:
        return 0
    get_vector_store().add_documents(chunks)
    return len(chunks)


def similarity_search(query: str, k: int | None = None) -> list[tuple[Document, float]]:
    k = k or settings.top_k
    return get_vector_store().similarity_search_with_score(query, k=k)


def list_sources() -> list[dict]:
    sql = text(
        """
        SELECT e.cmetadata->>'source' AS source, COUNT(*) AS chunk_count
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE c.name = :collection_name
        GROUP BY 1
        ORDER BY 1
        """
    )
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(sql, {"collection_name": settings.collection_name})
            return [{"source": row.source, "chunk_count": row.chunk_count} for row in rows]
    except Exception:  # noqa: BLE001 - 集合还没建过（首次运行）时按空知识库处理
        return []


def clear_knowledge_base() -> int:
    sql = text(
        """
        DELETE FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = :collection_name
        )
        """
    )
    try:
        with get_engine().begin() as conn:
            result = conn.execute(sql, {"collection_name": settings.collection_name})
            return result.rowcount or 0
    except Exception:  # noqa: BLE001 - 集合还没建过时没什么可清空的
        return 0


def delete_source(source: str) -> int:
    sql = text(
        """
        DELETE FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = :collection_name
        )
        AND cmetadata->>'source' = :source
        """
    )
    try:
        with get_engine().begin() as conn:
            result = conn.execute(sql, {"collection_name": settings.collection_name, "source": source})
            return result.rowcount or 0
    except Exception:  # noqa: BLE001 - 集合还没建过时没什么可删的
        return 0
