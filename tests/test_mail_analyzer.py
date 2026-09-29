"""轻量测试：邮件 LLM 分析的提示词拼装与输出解析（LLM 用假函数代替）。

运行：
    python tests/test_mail_analyzer.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document

from backend.mail_analyzer import (
    ANALYZE_SYSTEM,
    ANSWER_SYSTEM,
    Analysis,
    Answer,
    analyze_email,
    answer_question,
    parse_json_object,
)

CHUNKS = [(Document(page_content="退款在订单页申请", metadata={"source": "faq.pdf"}), 0.2)]


def _llm_returning(output: str):
    calls = []

    def llm(messages):
        calls.append(messages)
        return output

    llm.calls = calls
    return llm


def test_parse_json_object_tolerates_code_fences():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_object_allows_raw_newlines_in_strings():
    # 多段落回答：字符串里是真实换行而不是 \n 转义
    text = '{"answered": true, "answer": "第一段 [1]\n第二段 [2]"}'
    assert parse_json_object(text) == {"answered": True, "answer": "第一段 [1]\n第二段 [2]"}


def test_parse_json_object_raises_without_json():
    for bad in ("sorry, I can't", "{not json}"):
        try:
            parse_json_object(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {bad!r}")


def test_analyze_email_parses_questions_and_wraps_email_as_data():
    llm = _llm_returning('{"category":"question","language":"zh","questions":["怎么退款？"," ","几点发货？"]}')
    result = analyze_email("咨询", "怎么退款？几点发货？", "en", llm)
    assert result == Analysis("question", "zh", ["怎么退款？", "几点发货？"])
    system, user = llm.calls[0]
    assert system["content"] == ANALYZE_SYSTEM
    assert user["content"].startswith("<email>") and user["content"].endswith("</email>")


def test_analyze_email_normalizes_bad_values():
    llm = _llm_returning('{"category":"weird","language":"fr","questions":[]}')
    assert analyze_email("s", "b", "en", llm) == Analysis("other", "en", [])
    # 声称是提问但没拆出任何问题 → 按 other 处理
    llm = _llm_returning('{"category":"question","language":"en","questions":[]}')
    assert analyze_email("s", "b", "zh", llm) == Analysis("other", "en", [])


def test_answer_question_keeps_only_valid_citations():
    llm = _llm_returning('{"answered": true, "answer": "请在订单页申请退款 [1][3]"}')
    result = answer_question("怎么退款？", CHUNKS, "zh", llm)
    assert result == Answer(True, "请在订单页申请退款 [1][3]", [1])
    system, user = llm.calls[0]
    assert system["content"] == ANSWER_SYSTEM
    assert "[1] 退款在订单页申请" in user["content"]
    assert user["content"].endswith("【问题】\n怎么退款？")


def test_answer_without_citation_or_answered_false_is_not_answered():
    llm = _llm_returning('{"answered": true, "answer": "请在订单页申请退款"}')
    assert answer_question("q", CHUNKS, "zh", llm) == Answer(False, "", [])
    llm = _llm_returning('{"answered": false, "answer": ""}')
    assert answer_question("q", CHUNKS, "zh", llm) == Answer(False, "", [])


def test_non_list_questions_treated_as_empty():
    llm = _llm_returning('{"category":"question","language":"zh","questions":"怎么退款"}')
    assert analyze_email("s", "b", "zh", llm) == Analysis("other", "zh", [])


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
    print("OK: mail analyzer tests passed")
