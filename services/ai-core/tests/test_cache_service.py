import unittest

from services.cache_service import TTLCache


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class TTLCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.cache = TTLCache(
            ttl_seconds=10,
            max_entries=2,
            clock=self.clock,
        )

    def test_repeated_key_hits_cache(self) -> None:
        calls = 0

        def factory():
            nonlocal calls
            calls += 1
            return "value"

        first_value, first_hit = self.cache.get_or_set("key", factory)
        second_value, second_hit = self.cache.get_or_set("key", factory)

        self.assertEqual(first_value, second_value)
        self.assertFalse(first_hit)
        self.assertTrue(second_hit)
        self.assertEqual(calls, 1)
        self.assertEqual(self.cache.stats().hit_rate, 50.0)

    def test_expired_entry_is_refreshed(self) -> None:
        self.cache.get_or_set("key", lambda: "old")
        self.clock.advance(11)

        value, cache_hit = self.cache.get_or_set("key", lambda: "new")

        self.assertEqual(value, "new")
        self.assertFalse(cache_hit)

    def test_oldest_entry_is_evicted_at_capacity(self) -> None:
        self.cache.get_or_set("first", lambda: 1)
        self.cache.get_or_set("second", lambda: 2)
        self.cache.get_or_set("third", lambda: 3)

        self.assertEqual(self.cache.stats().size, 2)
        self.assertEqual(self.cache.stats().evictions, 1)

    def test_clear_returns_removed_entry_count(self) -> None:
        self.cache.get_or_set("first", lambda: 1)
        self.cache.get_or_set("second", lambda: 2)

        self.assertEqual(self.cache.clear(), 2)
        self.assertEqual(self.cache.stats().size, 0)
