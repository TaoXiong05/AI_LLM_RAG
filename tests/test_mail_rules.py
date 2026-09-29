"""轻量测试：邮件纯规则处理。

运行：
    python tests/test_mail_rules.py
"""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.mail_rules import (
    detect_lang,
    extract_body,
    has_attachments,
    html_to_text,
    is_addressed_to,
    is_auto_generated,
    is_spoofed,
    precheck,
    sender_address,
    strip_quoted,
)

OWN = "support@taoxiong.site"


def test_sender_address_parses_display_name():
    assert sender_address({"from": "Alice <Alice@Example.com>"}) == "alice@example.com"
    assert sender_address({}) == ""


def test_is_addressed_to_checks_to_cc_and_received_for():
    assert is_addressed_to({"to": ["Support <support@taoxiong.site>"]}, OWN)
    assert is_addressed_to({"to": ["x@a.com"], "cc": ["SUPPORT@taoxiong.site"]}, OWN)
    assert is_addressed_to({"to": ["x@a.com"], "received_for": ["support@taoxiong.site"]}, OWN)
    assert not is_addressed_to({"to": ["sales@taoxiong.site"]}, OWN)


def test_auto_generated_by_headers_and_localpart():
    base = {"from": "bob@example.com", "headers": {}}
    assert not is_auto_generated(base, OWN)
    assert not is_auto_generated({**base, "headers": {"Auto-Submitted": "no"}}, OWN)
    assert is_auto_generated({**base, "headers": {"Auto-Submitted": "auto-replied"}}, OWN)
    assert is_auto_generated({**base, "headers": {"List-Id": "<x.list>"}}, OWN)
    assert is_auto_generated({**base, "headers": {"Precedence": "bulk"}}, OWN)
    assert is_auto_generated({"from": "no-reply@github.com"}, OWN)
    assert is_auto_generated({"from": "MAILER-DAEMON@mx.example.com"}, OWN)
    assert is_auto_generated({"from": OWN}, OWN)  # 自己发给自己，防回环
    assert is_auto_generated({}, OWN)  # 没有发件人无法回复


def test_is_spoofed_only_on_dmarc_fail():
    assert is_spoofed({"authentication": {"dmarc": "fail"}})
    assert not is_spoofed({"authentication": {"dmarc": "pass"}})
    assert not is_spoofed({"authentication": {"dmarc": None}})
    assert not is_spoofed({})


def test_html_to_text_drops_tags_scripts_and_blockquotes():
    markup = "<div>Hello <b>world</b></div><script>x()</script><blockquote>old reply</blockquote><p>Bye</p>"
    text = html_to_text(markup)
    assert "Hello" in text and "world" in text and "Bye" in text
    assert "x()" not in text and "old reply" not in text


def test_html_to_text_decodes_base64_data_uri():
    payload = base64.b64encode("<p>你好</p>".encode()).decode()
    assert html_to_text(f"data:text/html;base64,{payload}") == "你好"


def test_strip_quoted_removes_history():
    text = "How do I reset?\n\nOn Mon, Sep 28, 2026 at 9:00 AM Support <support@taoxiong.site> wrote:\n> old answer"
    assert strip_quoted(text) == "How do I reset?"
    assert strip_quoted("问题一\n\n在 2026年9月28日 写道：\n> 旧内容") == "问题一"
    assert strip_quoted("line1\n> quoted\nline2") == "line1\nline2"


def test_extract_body_prefers_text_and_falls_back_to_html():
    assert extract_body({"text": "plain", "html": "<p>html</p>"}) == "plain"
    assert extract_body({"text": None, "html": "<p>html</p>"}) == "html"
    assert extract_body({}) == ""


def test_detect_lang():
    assert detect_lang("请问如何退款？") == "zh"
    assert detect_lang("How do I get a refund?") == "en"
    assert detect_lang("Hi, 我想问一下退款流程") == "zh"
    assert detect_lang("") == "en"


def test_has_attachments_ignores_inline_images():
    assert not has_attachments({"attachments": [{"content_disposition": "inline"}]})
    assert has_attachments({"attachments": [{"content_disposition": None}]})
    assert has_attachments({"attachments": [{"content_disposition": "attachment"}]})
    assert not has_attachments({})


def test_html_to_text_malformed_base64_data_uri_is_empty():
    assert html_to_text("data:text/html;base64,abc") == ""


def test_extract_body_whitespace_text_falls_back_to_html():
    assert extract_body({"text": "  \n", "html": "<p>html</p>"}) == "html"


def test_precheck():
    assert precheck("", has_attachments=False, max_chars=100) == "empty"
    assert precheck("  ", has_attachments=True, max_chars=100) == "attachment_only"
    assert precheck("x" * 101, has_attachments=False, max_chars=100) == "too_long"
    assert precheck("ok", has_attachments=True, max_chars=100) is None


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
    print("OK: mail rules tests passed")
