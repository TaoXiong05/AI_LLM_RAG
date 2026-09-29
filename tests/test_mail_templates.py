"""轻量测试：邮件回复模板与正文拼装。

运行：
    python tests/test_mail_templates.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.mail_templates import (
    TEMPLATES,
    AnswerItem,
    answers_reply,
    compose_answers,
    render_template,
    reply_subject,
    template_reply,
    thread_headers,
)


def test_answers_html_structure_and_escaping():
    items = [
        AnswerItem("What is <MCP>?", "Para one [1].\n\nPara two [2].", ["[1][2] a.docx"]),
        AnswerItem("Opening hours?", None, []),
    ]
    reply = answers_reply(items, "en", truncated_limit=5, attachment_note=True)
    assert reply.text == compose_answers(items, "en", truncated_limit=5, attachment_note=True)
    h = reply.html
    assert h.startswith("<!doctype html>") and h.endswith("</html>")
    assert "What is &lt;MCP&gt;?" in h and "<MCP>" not in h  # 来信内容必须转义
    assert h.count("<p ") >= 2 and "Para two" in h  # 空行分段
    assert "[1]</sup>" in h  # 引用编号渲染为上标
    assert "<b>[1]</b><b>[2]</b> a.docx" in h  # 参考来源带编号
    assert "Question 2" in h and TEMPLATES["en"]["not_found_short"] in h
    assert TEMPLATES["en"]["truncated"].format(n=5)[:20] in h
    assert "generated automatically by AI" in h and TEMPLATES["en"]["reply_hint"] in h


def test_template_reply_has_both_versions():
    reply = template_reply("too_long", "zh", n=5000)
    assert reply.text == render_template("too_long", "zh", n=5000)
    assert "5000" in reply.html and "RAG 智能客服" in reply.html


def test_zh_and_en_have_the_same_keys():
    assert TEMPLATES["zh"].keys() == TEMPLATES["en"].keys()


def test_render_template_fills_values_and_appends_signature():
    text = render_template("too_long", "zh", n=5000)
    assert "5000" in text
    assert text.endswith(TEMPLATES["zh"]["signature"])


def test_render_template_ignores_unused_kwargs_and_unknown_lang():
    assert render_template("busy", "fr", n=1) == render_template("busy", "en")


def test_compose_answers_lists_each_question():
    items = [
        AnswerItem("怎么退款？", "在订单页申请 [1]", ["faq.pdf", "policy.docx"]),
        AnswerItem("几点下班？", None, []),
    ]
    text = compose_answers(items, "zh", truncated_limit=None, attachment_note=False)
    assert text.startswith(TEMPLATES["zh"]["greeting"])
    assert "问题 1：怎么退款？" in text
    assert "回答：在订单页申请 [1]" in text
    assert "参考来源：faq.pdf、policy.docx" in text
    assert "问题 2：几点下班？\n" + TEMPLATES["zh"]["not_found"] in text
    assert text.endswith(TEMPLATES["zh"]["signature"])
    assert TEMPLATES["zh"]["truncated"].format(n=5) not in text
    assert TEMPLATES["zh"]["attachment_note"] not in text


def test_compose_answers_notes():
    items = [AnswerItem("Q?", "A [1]", ["a.pdf", "b.pdf"])]
    text = compose_answers(items, "en", truncated_limit=5, attachment_note=True)
    assert "Sources: a.pdf, b.pdf" in text
    assert TEMPLATES["en"]["truncated"].format(n=5) in text
    assert TEMPLATES["en"]["attachment_note"] in text


def test_reply_subject():
    assert reply_subject("退款问题") == "Re: 退款问题"
    assert reply_subject("RE: hi") == "RE: hi"
    assert reply_subject("  ") == "Re:"
    assert reply_subject(None) == "Re:"


def test_thread_headers():
    email = {"message_id": "<b@x>", "headers": {"References": "<a@x>"}}
    assert thread_headers(email) == {"In-Reply-To": "<b@x>", "References": "<a@x> <b@x>"}
    assert thread_headers({"message_id": "<b@x>"}) == {"In-Reply-To": "<b@x>", "References": "<b@x>"}
    assert thread_headers({}) == {}


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
    print("OK: mail templates tests passed")
