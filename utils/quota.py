import threading
from datetime import datetime, timezone

SESSION_STEP_CAP = 6        # per browser session. Parse = 1 step, analysis = 1 step
DAILY_DEMO_LIMIT = 120      # across all visitors, resets at 00:00 UTC. Lower it if your key limits are tight


class DailyCap:
    """In-memory shared counter. Resets on restart, which only makes it more generous."""

    def __init__(self, limit: int, today_fn=None):
        self.limit = limit
        self._today = today_fn or (lambda: datetime.now(timezone.utc).date())
        self._day, self._used = self._today(), 0
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            d = self._today()
            if d != self._day:
                self._day, self._used = d, 0
            if self._used >= self.limit:
                return False
            self._used += 1
            return True


DEMO_CAP = DailyCap(DAILY_DEMO_LIMIT)
