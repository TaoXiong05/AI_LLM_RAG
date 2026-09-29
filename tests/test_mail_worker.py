"""轻量测试：邮件 worker 全流程（SQLite 内存库 + 假 Resend 客户端 + 假 LLM + 假检索）。

运行：
    python tests/test_mail_worker.py
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document
from sqlalchemy import create_engine, text

from backend import mail_analyzer, mail_log
from backend.mail_templates import TEMPLATES, render_template
from backend.mail_worker import Deps, WorkerConfig, poll_once

# 失败路径的测试会故意触发 log.exception / log.warning，静音日志以保持输出干净
logging.disable(logging.CRITICAL)

OWN = "support@taoxiong.site"
NOW = 1_790_000_000.0  # 固定时钟：2026-09
CHUNK = [(Document(page_content="退款请在订单页申请", metadata={"source": "faq.pdf"}), 0.2)]


def make_email(eid="e1", body="怎么退款？", **overrides) -> dict:
    email = {
        "id": eid,
        "from": "Alice <alice@example.com>",
        "to": [OWN],
        "subject": "咨询",
        "text": body,
        "html": None,
        "headers": {},
        "message_id": f"<{eid}@example.com>",
        "attachments": [],
        "authentication": {"dmarc": "pass"},
        "created_at": datetime.fromtimestamp(NOW - 60, timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    email.update(overrides)
    return email


class FakeClient:
    def __init__(self, emails):
        self.emails = {e["id"]: e for e in emails}
        self.sent: list[dict] = []
        self.fetched: list[str] = []
        self.fail_send = False
        self.fail_fetch = False

    def list_received(self, limit=100):
        # 与 Resend 一致：最新的在前
        return [{"id": e["id"], "created_at": e["created_at"]} for e in reversed(list(self.emails.values()))]

    def get_received(self, email_id):
        self.fetched.append(email_id)
        if self.fail_fetch:
            raise RuntimeError("fetch down")
        return self.emails[email_id]

    def send(self, **kwargs):
        if self.fail_send:
            raise RuntimeError("resend down")
        self.sent.append(kwargs)
        return f"sent-{len(self.sent)}"


class FakeLLM:
    """按 system prompt 区分：分析调用返回固定 analysis；作答调用按问题查 answers（没有则 answered=false）。"""

    def __init__(self, analysis, answers=None, fail=False):
        self.analysis = analysis
        self.answers = answers or {}
        self.fail = fail
        self.calls = 0

    def __call__(self, messages):
        self.calls += 1
        if self.fail:
            raise RuntimeError("llm down")
        if messages[0]["content"] == mail_analyzer.ANALYZE_SYSTEM:
            return json.dumps(self.analysis, ensure_ascii=False)
        question = messages[1]["content"].split("【问题】\n", 1)[1]
        answer = self.answers.get(question)
        return json.dumps({"answered": answer is not None, "answer": answer or ""}, ensure_ascii=False)


def make_deps(emails, llm, kb=None, **overrides) -> Deps:
    engine = create_engine("sqlite://")
    mail_log.ensure_table(engine)
    cfg = dict(
        mail_from=f"RAG Support <{OWN}>",
        mail_address=OWN,
        per_sender_daily_limit=5,
        daily_global_limit=50,
        max_questions=5,
        max_body_chars=5000,
        max_retries=3,
        max_age_hours=24,
    )
    cfg.update(overrides)
    kb = kb or {}
    return Deps(
        engine=engine,
        client=FakeClient(emails),
        retrieve=lambda q: kb.get(q, []),
        llm=llm,
        config=WorkerConfig(**cfg),
        clock=lambda: NOW,
    )


def _category(deps, resend_id="e1"):
    with deps.engine.connect() as conn:
        return conn.execute(
            text("SELECT category FROM email_log WHERE resend_id = :id"), {"id": resend_id}
        ).scalar()


def _question_llm(*questions, answers=None):
    return FakeLLM({"category": "question", "language": "zh", "questions": list(questions)}, answers)


def test_answers_question_from_kb():
    llm = _question_llm("怎么退款？", answers={"怎么退款？": "请在订单页申请 [1]"})
    deps = make_deps([make_email()], llm, kb={"怎么退款？": CHUNK})
    poll_once(deps)
    [sent] = deps.client.sent
    assert sent["from_"] == f"RAG Support <{OWN}>"
    assert sent["to"] == "alice@example.com"
    assert sent["subject"] == "Re: 咨询"
    assert sent["headers"] == {"In-Reply-To": "<e1@example.com>", "References": "<e1@example.com>"}
    assert sent["idempotency_key"] == "reply-e1"
    assert "回答：请在订单页申请 [1]" in sent["text"]
    assert "参考来源：[1] faq.pdf" in sent["text"]
    assert sent["text"].endswith(TEMPLATES["zh"]["signature"])
    # 同时发送 HTML 版本
    assert "请在订单页申请" in sent["html"] and "faq.pdf" in sent["html"]
    assert "问题 1" in sent["html"] and "RAG 智能客服" in sent["html"]
    assert mail_log.get_status(deps.engine, "e1") == ("replied", 0)
    assert _category(deps) == "answered"


def test_template_replies_also_send_html():
    deps = make_deps([make_email(body="")], FakeLLM({}))
    poll_once(deps)
    assert deps.client.sent[0]["html"].startswith("<!doctype html>")


def test_sources_list_the_citation_numbers_per_file():
    chunks = [
        (Document(page_content="片段一", metadata={"source": "a.docx"}), 0.1),
        (Document(page_content="片段二", metadata={"source": "b.pdf"}), 0.2),
        (Document(page_content="片段三", metadata={"source": "a.docx"}), 0.3),
    ]
    llm = _question_llm("什么是 MCP？", answers={"什么是 MCP？": "定义 [3]。架构 [1][2]。"})
    deps = make_deps([make_email()], llm, kb={"什么是 MCP？": chunks})
    poll_once(deps)
    # 按首次引用顺序列出文件，每个文件带上正文中用到的全部编号
    assert "参考来源：[1][3] a.docx、[2] b.pdf" in deps.client.sent[0]["text"]


def test_mixed_found_and_not_found():
    llm = _question_llm("怎么退款？", "几点下班？", answers={"怎么退款？": "请在订单页申请 [1]"})
    deps = make_deps([make_email(body="怎么退款？几点下班？")], llm, kb={"怎么退款？": CHUNK})
    poll_once(deps)
    body = deps.client.sent[0]["text"]
    assert "问题 1：怎么退款？" in body
    assert "问题 2：几点下班？\n" + TEMPLATES["zh"]["not_found"] in body


def test_llm_refusal_counts_as_not_found():
    # 检索到了片段，但 LLM 判断资料不足 → 该题按未检索到处理
    llm = _question_llm("怎么退款？")
    deps = make_deps([make_email()], llm, kb={"怎么退款？": CHUNK})
    poll_once(deps)
    assert deps.client.sent[0]["text"] == render_template("all_not_found", "zh")
    assert _category(deps) == "not_found"


def test_all_not_found_skips_answer_llm_call():
    llm = _question_llm("几点下班？")
    deps = make_deps([make_email(body="几点下班？")], llm)
    poll_once(deps)
    assert deps.client.sent[0]["text"] == render_template("all_not_found", "zh")
    assert llm.calls == 1  # 只有分析调用；没有检索结果就不调用作答


def test_truncates_to_max_questions():
    questions = [f"问题{i}？" for i in range(7)]
    llm = _question_llm(*questions, answers={q: "答 [1]" for q in questions})
    deps = make_deps([make_email()], llm, kb={q: CHUNK for q in questions})
    poll_once(deps)
    body = deps.client.sent[0]["text"]
    assert "问题 5：" in body and "问题 6：" not in body
    assert TEMPLATES["zh"]["truncated"].format(n=5) in body


def test_attachment_with_question_adds_note():
    llm = _question_llm("怎么退款？", answers={"怎么退款？": "请在订单页申请 [1]"})
    email = make_email(attachments=[{"content_disposition": "attachment", "filename": "a.pdf"}])
    deps = make_deps([email], llm, kb={"怎么退款？": CHUNK})
    poll_once(deps)
    assert TEMPLATES["zh"]["attachment_note"] in deps.client.sent[0]["text"]


def test_rule_based_silence():
    cases = [
        (make_email(headers={"Auto-Submitted": "auto-replied"}), "auto_generated"),
        (make_email(to=["sales@taoxiong.site"]), "ignored_recipient"),
        (make_email(authentication={"dmarc": "fail"}), "spoofed"),
    ]
    for email, category in cases:
        llm = _question_llm("x")
        deps = make_deps([email], llm)
        poll_once(deps)
        assert deps.client.sent == [], category
        assert mail_log.get_status(deps.engine, "e1") == ("silent", 0)
        assert _category(deps) == category
        assert llm.calls == 0


def test_precheck_templates():
    cases = [
        (make_email(body=""), "empty"),
        (make_email(body="", attachments=[{"content_disposition": "attachment"}]), "attachment_only"),
        (make_email(body="长" * 5001), "too_long"),
    ]
    for email, category in cases:
        llm = FakeLLM({})
        deps = make_deps([email], llm)
        poll_once(deps)
        # 主题"咨询"是中文，所以按中文模板
        assert deps.client.sent[0]["text"] == render_template(category, "zh", n=5000), category
        assert _category(deps) == category
        assert llm.calls == 0


def test_llm_categories():
    for category in ("spam", "abuse"):
        deps = make_deps([make_email()], FakeLLM({"category": category, "language": "zh", "questions": []}))
        poll_once(deps)
        assert deps.client.sent == [], category
        assert _category(deps) == category
    # 感谢 / 问候 / 没识别出问题：回一封"怎么提问"的提示
    deps = make_deps([make_email()], FakeLLM({"category": "other", "language": "zh", "questions": []}))
    poll_once(deps)
    assert deps.client.sent[0]["text"] == render_template("no_question", "zh")
    assert _category(deps) == "other"
    assert mail_log.get_status(deps.engine, "e1") == ("replied", 0)
    deps = make_deps([make_email()], FakeLLM({"category": "injection", "language": "en", "questions": []}))
    poll_once(deps)
    assert deps.client.sent[0]["text"] == render_template("injection", "en")
    assert _category(deps) == "injection"


def test_sender_daily_limit_sends_one_notice_then_silence():
    llm = _question_llm("怎么退款？", answers={"怎么退款？": "答 [1]"})
    emails = [make_email(f"e{i}") for i in range(7)]
    deps = make_deps(emails, llm, kb={"怎么退款？": CHUNK})
    poll_once(deps)
    assert len(deps.client.sent) == 6
    assert deps.client.sent[5]["text"] == render_template("sender_limit", "zh", n=5)
    assert _category(deps, "e5") == "sender_limit_notice"
    assert _category(deps, "e6") == "sender_limit_silent"


def test_global_daily_limit_is_silent():
    llm = _question_llm("怎么退款？", answers={"怎么退款？": "答 [1]"})
    emails = [make_email("e0"), make_email("e1", **{"from": "Bob <bob@example.com>"})]
    deps = make_deps(emails, llm, kb={"怎么退款？": CHUNK}, daily_global_limit=1)
    poll_once(deps)
    assert len(deps.client.sent) == 1
    assert _category(deps, "e1") == "global_limit"


def test_llm_failure_retries_then_sends_busy():
    deps = make_deps([make_email()], FakeLLM({}, fail=True), max_retries=3)
    poll_once(deps)
    poll_once(deps)
    assert deps.client.sent == []
    assert mail_log.get_status(deps.engine, "e1") == ("pending", 2)
    poll_once(deps)
    [sent] = deps.client.sent
    assert sent["text"] == render_template("busy", "zh")
    assert sent["idempotency_key"] == "busy-e1"
    assert mail_log.get_status(deps.engine, "e1") == ("replied", 3)
    assert _category(deps) == "busy"
    poll_once(deps)
    assert len(deps.client.sent) == 1  # 终态不再处理


def test_busy_send_failure_marks_failed():
    deps = make_deps([make_email()], FakeLLM({}, fail=True), max_retries=1)
    deps.client.fail_send = True
    poll_once(deps)
    assert mail_log.get_status(deps.engine, "e1") == ("failed", 1)
    assert _category(deps) == "busy_send_failed"


def test_processes_each_email_once():
    llm = _question_llm("怎么退款？", answers={"怎么退款？": "答 [1]"})
    deps = make_deps([make_email()], llm, kb={"怎么退款？": CHUNK})
    poll_once(deps)
    poll_once(deps)
    assert len(deps.client.sent) == 1
    assert deps.client.fetched == ["e1"]


def test_skips_emails_older_than_max_age():
    deps = make_deps([make_email(created_at="2020-01-01T00:00:00.000Z")], FakeLLM({}))
    poll_once(deps)
    assert deps.client.sent == []
    assert deps.client.fetched == []
    assert mail_log.get_status(deps.engine, "e1") is None


def test_fetch_failure_on_pending_row_is_bounded():
    deps = make_deps([make_email()], FakeLLM({}, fail=True), max_retries=3)
    poll_once(deps)
    assert mail_log.get_status(deps.engine, "e1") == ("pending", 1)
    deps.client.fail_fetch = True
    poll_once(deps)
    poll_once(deps)
    assert mail_log.get_status(deps.engine, "e1") == ("failed", 3)
    assert _category(deps) == "fetch_failed"
    assert deps.client.sent == []


def test_fetch_failure_on_new_email_is_not_logged():
    deps = make_deps([make_email()], FakeLLM({}))
    deps.client.fail_fetch = True
    poll_once(deps)
    assert mail_log.get_status(deps.engine, "e1") is None
    assert deps.client.sent == []


def test_exhausted_pending_row_goes_straight_to_busy():
    llm = _question_llm("怎么退款？", answers={"怎么退款？": "答 [1]"})
    deps = make_deps([make_email()], llm, kb={"怎么退款？": CHUNK}, max_retries=3)
    mail_log.start(deps.engine, "e1", message_id="<e1@example.com>", sender="alice@example.com", subject="咨询", now=NOW)
    for _ in range(3):
        mail_log.bump_retry(deps.engine, "e1", error="x", now=NOW)
    assert mail_log.get_status(deps.engine, "e1") == ("pending", 3)
    poll_once(deps)
    [sent] = deps.client.sent
    assert sent["idempotency_key"] == "busy-e1"
    assert sent["text"] == render_template("busy", "zh")
    assert llm.calls == 0
    assert mail_log.get_status(deps.engine, "e1") == ("replied", 3)


def test_unparseable_email_reaches_terminal_state():
    from backend import mail_rules

    deps = make_deps([make_email(text=None, html="data:text/html;base64,abc")], FakeLLM({}), max_retries=3)
    original = mail_rules.extract_body

    def boom(email):
        raise ValueError("bad body")

    mail_rules.extract_body = boom  # 临时让解析必然失败，模拟无法处理的邮件
    try:
        for _ in range(3):
            poll_once(deps)
        assert mail_log.get_status(deps.engine, "e1") == ("failed", 3)
        assert _category(deps) == "give_up_error"
        assert deps.client.sent == []
        fetched = len(deps.client.fetched)
        poll_once(deps)
        assert len(deps.client.fetched) == fetched  # 终态不再读取详情
    finally:
        mail_rules.extract_body = original


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
    print("OK: mail worker tests passed")
