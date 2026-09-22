import time

class RateLimiter:
    def __init__(self, max_per_minute: int = 10):
        self._max = max_per_minute
        self._timestamps: list[float] = []

    def allow(self) -> bool:
        now = time.monotonic()
        self._timestamps = [t for t in self._timestamps if now - t < 60]
        if len(self._timestamps) >= self._max:
            return False
        self._timestamps.append(now)
        return True
