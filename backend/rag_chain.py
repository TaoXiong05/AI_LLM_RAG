"""检索 + 拼 prompt + 调用 LLM 生成回答（流式），并带上引用来源。

回答语言跟随界面语言（lang = "zh" / "en"）：
- 整段输出（含开头的“找不着相关资料”声明）都用界面语言。
- 当知识库中找不到相关资料时，先输出对应语言的固定提示语，
  再由模型基于自身知识作答（网络搜索口径）。
"""
from collections.abc import Iterator
from functools import lru_cache
import re

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
    "如果你的回答确实基于某个参考资料片段，请在该句子的末尾标注对应的编号，"
    "格式为[数字]（例如[1]），且只标注你真正用到的编号；"
    "若参考资料完全不足以支撑回答，则不要标注任何编号。"
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
            "【规则】\n"
            "1. 如果这些参考资料足以回答用户的问题，请优先依据参考资料回答，"
            "并在你确实引用了某个片段的句子末尾标注其编号，例如 [1]、[2]（编号对应上面各条）。\n"
            "2. 只标注你实际用到的编号，不要编造。[i] 编号应紧跟在说明该片段内容的句子之后。\n"
            "3. 如果这些参考资料不足以回答用户的问题，请原样照搬下面这句话作为"
            "回答的开头（一字不差），且不要标注任何引用编号：\n"
            f"“{phrase}”\n\n"
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


# 模型回答里标注引用编号的格式：[1]、[2]、…（紧跟在引用该片段的句子后）
CITE_PATTERN = re.compile(r"\[(\d+)\]")


def parse_cited_indices(answer: str) -> list[int]:
    """从模型回答中提取被引用的片段编号（去重、保持出现顺序）。"""
    seen: list[int] = []
    for match in CITE_PATTERN.finditer(answer):
        idx = int(match.group(1))
        if idx >= 1 and idx not in seen:
            seen.append(idx)
    return seen


def select_cited_chunks(
    answer: str, chunks: list[tuple[Document, float]]
) -> list[tuple[Document, float]]:
    """根据回答中标注的引用编号，选出真正被回答引用的片段子集（保持编号顺序）。

    检索结果只是"候选"；只有当回答实际标注了 [i] 才代表该片段被引用。
    若回答以"未找到相关资料"声明开头且未标注任何编号，则返回空列表，
    与 UI 不再展示引用卡保持完全一致。
    """
    indices = parse_cited_indices(answer)
    return [chunks[idx - 1] for idx in indices if 1 <= idx <= len(chunks)]


def retrieve(question: str, k: int | None = None) -> list[tuple[Document, float]]:
    """第一步：在知识库中检索相关片段（同步、较快）。"""
    return db.similarity_search(question, k=k)


def generate(question: str, chunks: list[tuple[Document, float]], lang: str = "en") -> Iterator[str]:
    """第二步：基于检索结果流式生成回答（逐字输出）。chunks 为空时走网络搜索兜底。"""
    if not chunks:
        return _fallback_stream(question, lang)

    messages = build_messages(question, chunks, lang)

    def _gen() -> Iterator[str]:
        for piece in get_llm().stream(messages):
            if piece.content:
                yield piece.content

    return _gen()


def _fallback_stream(question: str, lang: str) -> Iterator[str]:
    yield NO_KB_PHRASE.get(lang, NO_KB_PHRASE["en"]) + "\n\n"
    messages = _build_messages(question, context=None, lang=lang)
    for piece in get_llm().stream(messages):
        if piece.content:
            yield piece.content
