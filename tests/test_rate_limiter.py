"""轻量测试：验证按 IP 的滑动窗口限流逻辑。

项目未引入 pytest，本文件用 assert + 直接运行的方式做冒烟验证。运行：
    python tests/test_rate_limiter.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.rate_limiter import RateLimiter


def test_allows_up_to_the_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60, ban_seconds=600)
    now = 1000.0
    assert limiter.check("1.2.3.4", now) is True
    assert limiter.check("1.2.3.4", now + 1) is True
    assert limiter.check("1.2.3.4", now + 2) is True


def test_blocks_once_limit_exceeded():
    limiter = RateLimiter(max_requests=2, window_seconds=60, ban_seconds=600)
    now = 1000.0
    assert limiter.check("1.2.3.4", now) is True
    assert limiter.check("1.2.3.4", now + 1) is True
    assert limiter.check("1.2.3.4", now + 2) is False


def test_stays_banned_for_the_full_ban_duration():
    limiter = RateLimiter(max_requests=1, window_seconds=60, ban_seconds=600)
    now = 1000.0
    assert limiter.check("1.2.3.4", now) is True
    assert limiter.check("1.2.3.4", now + 1) is False  # 触发封禁
    assert limiter.check("1.2.3.4", now + 599) is False  # 封禁期内
    assert limiter.check("1.2.3.4", now + 601) is True  # 封禁期已过，窗口也已过期


def test_window_expires_independently_per_key():
    limiter = RateLimiter(max_requests=2, window_seconds=60, ban_seconds=600)
    now = 1000.0
    assert limiter.check("1.2.3.4", now) is True
    assert limiter.check("1.2.3.4", now + 1) is True
    assert limiter.check("5.6.7.8", now + 1) is True  # 另一个 IP 不受影响
    assert limiter.check("1.2.3.4", now + 2) is False


def test_old_requests_fall_out_of_the_window():
    limiter = RateLimiter(max_requests=2, window_seconds=60, ban_seconds=600)
    now = 1000.0
    assert limiter.check("1.2.3.4", now) is True
    assert limiter.check("1.2.3.4", now + 30) is True
    # 窗口滑动后，第一次请求已过期，腾出了名额
    assert limiter.check("1.2.3.4", now + 61) is True


if __name__ == "__main__":
    test_allows_up_to_the_limit()
    test_blocks_once_limit_exceeded()
    test_stays_banned_for_the_full_ban_duration()
    test_window_expires_independently_per_key()
    test_old_requests_fall_out_of_the_window()
    print("OK: rate limiter tests passed")
