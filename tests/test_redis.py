from unittest import skipIf
import redis.asyncio as redis_lib
from async_lru_ttl_cache.core import async_lru_cache
from base_tests import BaseTestsAsyncLRUCache  # Импорт базового класса

@skipIf(redis_lib is None, "redis.asyncio not available")
class TestsRedisAsyncLRUCache(BaseTestsAsyncLRUCache):
    backend = 'redis'
    extra_kwargs = {'redis_url': 'redis://localhost:6379/0'}

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.redis = redis_lib.from_url(self.extra_kwargs['redis_url'])
        await self.redis.flushdb()

    async def asyncTearDown(self):
        await self.redis.close()
        await super().asyncTearDown()

    async def test_persistence(self):
        call_count = 0

        @async_lru_cache(maxsize=128, ttl=None, backend=self.backend, namespace="test_persistence", **self.extra_kwargs)
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

        await func(1)  # should hit from redis
        self.assertEqual(1, call_count)  # no new call

        stats = await func.cache_stats()
        self.assertEqual(1, stats['hits'])  # additional hit
        self.assertEqual(0, stats['misses'])  # no miss, loaded from redis

        # Clear to clean up
        await func.cache_clear()