"""轻量测试：email_log 表的状态流转与计数（SQLite 内存库，不连真实 Postgres）。

运行：
    python tests/test_mail_log.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text

from backend import mail_log


def _engine():
    engine = create_engine("sqlite://")
    mail_log.ensure_table(engine)
    mail_log.ensure_table(engine)  # 重复调用必须安全
    return engine


def test_start_is_idempotent_and_get_status():
    e = _engine()
    assert mail_log.get_status(e, "r1") is None
    mail_log.start(e, "r1", message_id="<m1>", sender="a@x.com", subject="s", now=100.0)
    mail_log.start(e, "r1", message_id="<m1>", sender="a@x.com", subject="s", now=200.0)
    assert mail_log.get_status(e, "r1") == ("pending", 0)


def test_bump_retry_then_finish():
    e = _engine()
    mail_log.start(e, "r1", message_id=None, sender="a@x.com", subject=None, now=100.0)
    assert mail_log.bump_retry(e, "r1", error="boom", now=101.0) == 1
    assert mail_log.bump_retry(e, "r1", error="boom", now=102.0) == 2
    mail_log.finish(e, "r1", status="replied", category="busy", now=103.0)
    assert mail_log.get_status(e, "r1") == ("replied", 2)
    # 终态不带 error 时保留最后一次重试的失败原因，方便事后排查
    with e.connect() as conn:
        assert conn.execute(text("SELECT error FROM email_log WHERE resend_id = 'r1'")).scalar() == "boom"


def test_count_replies_filters():
    e = _engine()
    day = mail_log.utc_day_start(86400 * 10 + 500)
    rows = [
        ("r1", "a@x.com", "replied", "answered", day + 1),
        ("r2", "a@x.com", "replied", "sender_limit_notice", day + 2),
        ("r3", "a@x.com", "silent", "spam", day + 3),
        ("r4", "b@x.com", "replied", "answered", day + 4),
        ("r5", "a@x.com", "replied", "answered", day - 1),  # 前一天
    ]
    for rid, sender, status, category, ts in rows:
        mail_log.start(e, rid, message_id=None, sender=sender, subject=None, now=ts)
        mail_log.finish(e, rid, status=status, category=category, now=ts)
    assert mail_log.count_replies(e, since=day) == 3
    assert mail_log.count_replies(e, since=day, sender="a@x.com") == 2
    assert mail_log.count_replies(e, since=day, sender="a@x.com", exclude_category="sender_limit_notice") == 1
    assert mail_log.count_replies(e, since=day, sender="a@x.com", category="sender_limit_notice") == 1


def test_utc_day_start():
    assert mail_log.utc_day_start(86400 * 3 + 123.4) == 86400 * 3


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
    print("OK: mail log tests passed")
