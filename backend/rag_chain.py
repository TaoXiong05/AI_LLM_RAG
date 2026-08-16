"""检索 + 拼 prompt + 调用 LLM 生成回答（流式），并带上引用来源。

回答语言跟随界面语言（lang = "zh" / "en"）：
- 整段输出（含开头的“找不着相关资料”声明）都用界面语言。
- 当知识库中找不到相关资料时，先输出对应语言的固定提示语，
  再由模型基于自身知识作答（网络搜索口径）。
"""
from collections.abc import Iterator
from functools import lru_cache

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from backend import db
from config import settings

# 界面语言代码 -> 给模型看的语言名（用于写进提示词）
LANG_NAME = {
    "en": "English",
    "zh": "中文",
}

# 未检索到相关资料时，回答开头输出的提示语（跟随界面语言）
NO_KB_PHRASE = {
    "en": "No relevant information was found in the knowledge base. "
          "The following answer is provided based on general knowledge (web-search style).",
    "zh": "知识库内部找不到相关资料，以下回答为网络搜索答案。",
}

SYSTEM_PROMPT = (
    "你是一个严谨、乐于助人的问答助手。"
    "请始终严格使用下面用户消息中指定的输出语言来回答整段内容（包括开头的任何声明）。"
    "当提供了参考资料时，优先依据参考资料回答；"
    "若参考资料不足以回答用户问题，必须原样照搬用户消息中给出的那句声明文字作为开头，"
    "再基于你自己掌握的知识给出尽量准确、有帮助的回答。"
)


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        streaming=True,
    )


def _lang_instruction(lang: str) -> str:
    name = LANG_NAME.get(lang, LANG_NAME["en"])
    return f"请使用界面语言（{name}）回答用户的问题，整段输出都用这种语言。"


def _build_messages(question: str, context: str | None, lang: str) -> list[dict]:
    language = _lang_instruction(lang)
    if context:
        phrase = NO_KB_PHRASE.get(lang, NO_KB_PHRASE["en"])
        user_content = (
            f"{language}\n\n"
            "请根据下面提供的参考资料回答用户的问题。\n\n"
            f"【参考资料】\n{context}\n\n"
            "【规则】如果这些参考资料不足以回答用户的问题，"
            f"请原样照搬下面这句话作为回答的开头（一字不差）：\n“{phrase}”\n\n"
            f"【问题】\n{question}"
        )
    else:
        user_content = (
            f"{language}\n\n"
            "当前知识库中未检索到相关资料，请你直接基于自己掌握的知识，"
            "给出一个尽量准确、有帮助的回答。\n\n"
            f"【问题】\n{question}"
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_messages(question: str, chunks: list[tuple[Document, float]], lang: str = "en") -> list[dict]:
    context = "\n\n".join(
        f"[{i}] {doc.page_content}" for i, (doc, _score) in enumerate(chunks, 1)
    )
    return _build_messages(question, context or None, lang)


def answer_stream(
    question: str, k: int | None = None, lang: str = "en"
) -> tuple[Iterator[str], list[tuple[Document, float]]]:
    chunks = db.similarity_search(question, k=k)

    if not chunks:
        # 未命中任何资料：先输出固定声明，再由模型基于自身知识作答（网络搜索口径）
        return _fallback_stream(question, lang), []

    messages = build_messages(question, chunks, lang)

    def _gen() -> Iterator[str]:
        for piece in get_llm().stream(messages):
            if piece.content:
                yield piece.content

    return _gen(), chunks


def _fallback_stream(question: str, lang: str) -> Iterator[str]:
    yield NO_KB_PHRASE.get(lang, NO_KB_PHRASE["en"]) + "\n\n"
    messages = _build_messages(question, context=None, lang=lang)
    for piece in get_llm().stream(messages):
        if piece.content:
            yield piece.content
