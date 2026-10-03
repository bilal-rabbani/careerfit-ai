import hashlib
import threading
import time
from collections import OrderedDict
from typing import Optional

PROMPT_VERSION = "v1"      # bump when you change a parser prompt or schema


class ParseCache:
    """In-memory LRU with expiry. Stores JSON strings so callers can't mutate cached objects."""

    def __init__(self, max_items: int = 50, ttl_seconds: int = 3600):
        self.max_items, self.ttl = max_items, ttl_seconds
        self._data: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def make_key(kind: str, text: str) -> str:
        raw = f"{PROMPT_VERSION}\x00{kind}\x00{text}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            stamp, value = item
            if time.time() - stamp > self.ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self):
        return len(self._data)


PARSE_CACHE = ParseCache()
