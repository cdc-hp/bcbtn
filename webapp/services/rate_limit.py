"""Giới hạn tần suất nộp hàng đợi — cùng thuật toán/ngưỡng với `lan_server.ApiServer` cũ
(cửa sổ trượt 10 lần/300 giây theo cặp khoá) để không lặp file trong request lớn khiến máy chủ
lỗi. Không dùng Redis (Section 10: "Không bắt buộc Redis hoặc Celery") — webapp chỉ chạy trên
đúng 1 tiến trình/1 máy chủ nên bộ nhớ trong tiến trình là đủ."""

from __future__ import annotations

import threading
import time
from collections import deque

RATE_LIMIT = 10
RATE_WINDOW_SECONDS = 300


class SlidingWindowRateLimiter:
    def __init__(self, limit: int = RATE_LIMIT, window_seconds: float = RATE_WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            times = self._hits.setdefault(key, deque())
            while times and now - times[0] > self.window_seconds:
                times.popleft()
            if len(times) >= self.limit:
                return False
            times.append(now)
            return True


queue_submit_limiter = SlidingWindowRateLimiter()
