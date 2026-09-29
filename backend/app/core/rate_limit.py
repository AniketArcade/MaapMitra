import threading
import time
from collections import defaultdict, deque

from slowapi import Limiter

from app.core.deps import get_client_ip

# In-memory storage. PRODUCTION SHORTCUT: resets on restart, not shared across instances.
limiter = Limiter(key_func=get_client_ip)


class SlidingWindow:
    """Per-key sliding-window counter (slowapi can't key on the request body)."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Record an attempt. Returns False if the key is over the limit."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_email_window = SlidingWindow(limit=5, window_seconds=60)
upload_window = SlidingWindow(limit=60, window_seconds=3600)  # per user


def reset_rate_limits() -> None:
    limiter.reset()
    login_email_window.reset()
    upload_window.reset()
