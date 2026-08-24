"""按 IP 的进程内滑动窗口限流：窗口期内超过阈值次数则封禁一段时间。"""
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float, ban_seconds: float):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._ban_seconds = ban_seconds
        self._lock = threading.Lock()
        self._requests: dict[str, deque] = defaultdict(deque)
        self._banned_until: dict[str, float] = {}

    def check(self, key: str, now: float | None = None) -> bool:
        """记录一次请求并返回是否放行；命中阈值或仍在封禁期内则拒绝。"""
        now = time.time() if now is None else now
        with self._lock:
            if now < self._banned_until.get(key, 0.0):
                return False

            window = self._requests[key]
            while window and window[0] <= now - self._window_seconds:
                window.popleft()

            if len(window) >= self._max_requests:
                self._banned_until[key] = now + self._ban_seconds
                return False

            window.append(now)
            return True
