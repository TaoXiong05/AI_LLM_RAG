"""检索 + 拼 prompt + 调用 LLM 生成回答（流式），并带上引用来源。"""
from collections.abc import Iterator
from functools import lru_cache

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from backend import db
from config import settings

SYSTEM_PROMPT = "你是一个严谨的问答助手，只依据提供的参考资料回答问题，资料中没有的信息请直接说不知道。"

EMPTY_KB_MESSAGE = "知识库为空或未检索到相关内容，请先在侧边栏上传并处理文档。"


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        streaming=True,
    )


def build_messages(question: str, chunks: list[tuple[Document, float]]) -> list[dict]:
    context = "\n\n".join(
        f"[{i}] {doc.page_content}" for i, (doc, _score) in enumerate(chunks, 1)
    )
    user_prompt = f"""请只根据下面提供的参考资料回答问题，如果参考资料中没有相关信息，请直接说不知道。

【参考资料】
{context}

【问题】
{question}"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def answer_stream(
    question: str, k: int | None = None, empty_message: str | None = None
) -> tuple[Iterator[str], list[tuple[Document, float]]]:
    chunks = db.similarity_search(question, k=k)

    if not chunks:
        return iter([empty_message or EMPTY_KB_MESSAGE]), []

    messages = build_messages(question, chunks)

    def _gen() -> Iterator[str]:
        for piece in get_llm().stream(messages):
            if piece.content:
                yield piece.content

    return _gen(), chunks
