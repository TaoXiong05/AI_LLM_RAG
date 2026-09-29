"""轻量测试：邮件相关配置的解析。

项目未引入 pytest，本文件用 assert + 直接运行的方式做冒烟验证。运行：
    python tests/test_mail_config.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings


def test_mail_address_is_parsed_and_lowercased():
    os.environ["MAIL_FROM"] = "Support Bot <Support@Taoxiong.site>"
    try:
        assert get_settings().mail_address == "support@taoxiong.site"
    finally:
        del os.environ["MAIL_FROM"]


def test_empty_mail_from_falls_back_to_default():
    # CI 里 vars.MAIL_FROM 未设置时会写出 "MAIL_FROM="，必须回退到默认值
    os.environ["MAIL_FROM"] = ""
    try:
        s = get_settings()
        assert s.mail_from == "RAG Support <support@taoxiong.site>"
        assert s.mail_address == "support@taoxiong.site"
    finally:
        del os.environ["MAIL_FROM"]


def test_mail_defaults():
    s = get_settings()
    assert s.mail_per_sender_daily_limit == 5
    assert s.mail_daily_global_limit == 50
    assert s.mail_max_questions == 5
    assert s.mail_max_body_chars == 5000
    assert s.mail_max_retries == 3
    assert s.mail_poll_seconds == 60
    assert s.mail_max_age_hours == 24


if __name__ == "__main__":
    for _name, _fn in list(globals().items()):
        if _name.startswith("test_"):
            _fn()
    print("OK: mail config tests passed")
