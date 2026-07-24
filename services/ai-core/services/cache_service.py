import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Generic, TypeVar


Key = TypeVar("Key")
Value = TypeVar("Value")


@dataclass(frozen=True)
class CacheStats:
    size: int
    max_entries: int
    ttl_seconds: int
    hits: int
    misses: int
    evictions: int
    hit_rate: float


@dataclass
class _CacheEntry(Generic[Value]):
    value: Value
    expires_at: float


class TTLCache(Generic[Key, Value]):
    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须大于 0")
        if max_entries <= 0:
            raise ValueError("max_entries 必须大于 0")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._entries: OrderedDict[Key, _CacheEntry[Value]] = OrderedDict()
        self._lock = RLock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get_or_set(
        self,
        key: Key,
        factory: Callable[[], Value],
    ) -> tuple[Value, bool]:
        with self._lock:
            now = self.clock()
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at > now:
                self._entries.move_to_end(key)
                self._hits += 1
                return entry.value, True
            if entry is not None:
                del self._entries[key]

            self._misses += 1
            value = factory()
            if len(self._entries) >= self.max_entries:
                self._entries.popitem(last=False)
                self._evictions += 1
            self._entries[key] = _CacheEntry(
                value=value,
                expires_at=now + self.ttl_seconds,
            )
            return value, False

    def clear(self) -> int:
        with self._lock:
            cleared = len(self._entries)
            self._entries.clear()
            return cleared

    def stats(self) -> CacheStats:
        with self._lock:
            total = self._hits + self._misses
            return CacheStats(
                size=len(self._entries),
                max_entries=self.max_entries,
                ttl_seconds=self.ttl_seconds,
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                hit_rate=round(self._hits / total * 100, 2) if total else 0.0,
            )
