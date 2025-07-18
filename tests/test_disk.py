import tempfile

from async_lru_ttl_cache.core import async_lru_cache
from base_tests import BaseTestsAsyncLRUCache


class TestsDiskAsyncLRUCache(BaseTestsAsyncLRUCache):
    backend = 'disk'

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.extra_kwargs = {'cache_dir': self.tmpdir.name}

    def tearDown(self):
        self.tmpdir.cleanup()
        super().tearDown()

    async def test_persistence(self):
        call_count = 0

        @async_lru_cache(maxsize=128, ttl=None, backend=self.backend, namespace="test_persistence",  **self.extra_kwargs)
        async def func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        await func(1)  # miss
        await func(1)  # hit

        self.assertEqual(1, call_count)

        stats = await func.cache_stats()
        self.assertEqual(1, stats['misses'])
        self.assertEqual(1, stats['hits'])

        # Force recreate cache
        del func._cache

        await func(1)  # should hit from disk
        self.assertEqual(1, call_count)  # no new call

        stats = await func.cache_stats()
        self.assertEqual(1, stats['hits'])  # additional hit
        self.assertEqual(0, stats['misses'])  # no miss, loaded from disk