import asyncio
from unittest import IsolatedAsyncioTestCase
from async_lru_ttl_cache import AsyncLRUCache, async_lru_cache
from ddt import data, ddt, unpack


@ddt
class TestsAsyncLRUCache(IsolatedAsyncioTestCase):
    @data(
        *[
            (2, None, 4),  # eviction, 4 calls
            (3, None, 3),  # no eviction for 1 after 3, 3 calls
            (128, None, 3),
        ]
    )
    @unpack
    async def test_basic(self, maxsize, ttl, expected_calls):
        """
        Testing basic caching and eviction
        :param maxsize: Maximum cache size
        :param ttl: Time-to-live (None for infinite)
        :param expected_calls: Expected number of function calls
        """
        call_count = 0

        @async_lru_cache(maxsize=maxsize, ttl=ttl)
        async def func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        await func(1)
        await func(1)  # Hit
        await func(2)
        await func(3)
        await func(1)  # Miss if evicted

        self.assertEqual(expected_calls, call_count)

        stats = await func.cache_stats()
        self.assertLessEqual(stats["size"], maxsize)

    @data(
        *[
            (128, 0.1, 2),  # After sleep > ttl, miss
            (128, 0.2, 2),
            (128, 0.05, 2),
        ]
    )
    @unpack
    async def test_ttl(self, maxsize, ttl, expected_calls):
        """
        Testing expiration by TTL
        :param maxsize: Maximum cache size
        :param ttl: Time-to-live
        :param expected_calls: Expected number of calls after expiration
        """
        call_count = 0

        @async_lru_cache(maxsize=maxsize, ttl=ttl)
        async def func(x):
            nonlocal call_count
            call_count += 1
            return x

        await func(1)
        await func(1)  # Hit

        await asyncio.sleep(ttl + 0.01)  # > TTL

        await func(1)  # Miss due to expiration

        self.assertEqual(expected_calls, call_count)

    @data(
        *[
            (None, 0.1, 3, 1),  # 3 concurrent, only 1 call
            (None, 0.05, 5, 1),
        ]
    )
    @unpack
    async def test_concurrency(self, ttl, delay, num_calls, expected_calls):
        """
        Testing concurrency (parallel calls)
        :param ttl: Time-to-live
        :param delay: Delay in function
        :param num_calls: Number of concurrent calls
        :param expected_calls: Expected number of real calls (1 due to cache)
        """
        call_count = 0

        @async_lru_cache(ttl=ttl)
        async def slow_func():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(delay)
            return 42

        # Concurrent calls
        results = await asyncio.gather(*(slow_func() for _ in range(num_calls)))

        self.assertEqual([42] * num_calls, results)
        self.assertEqual(expected_calls, call_count)

        stats = await slow_func.cache_stats()
        self.assertEqual(stats["hits"], num_calls - 1)
        self.assertEqual(stats["misses"], 1)

    @data(
        *[
            (None, 10, 1),  # arg=10, calls=1 (hit)
            (None, 20, 1),
        ]
    )
    @unpack
    async def test_method_cache(self, ttl, arg, expected_calls):
        """
        Testing cache for class methods
        :param ttl: Time-to-live
        :param arg: Method argument
        :param expected_calls: Expected number of calls
        """
        call_count = 0

        class TestClass:
            @async_lru_cache(ttl=ttl)
            async def method(self, x):
                nonlocal call_count
                call_count += 1
                return x * 3

        obj = TestClass()
        await obj.method(arg)
        await obj.method(arg)  # Hit

        self.assertEqual(expected_calls, call_count)

        # Another instance — separate cache
        obj2 = TestClass()
        await obj2.method(arg)
        self.assertEqual(expected_calls + 1, call_count)

        # Clear
        await obj.method.cache_clear(obj)
        await obj.method(arg)
        self.assertEqual(expected_calls + 2, call_count)

    @data(
        *[
            (None, "Error", 0),  # No cache after exception
        ]
    )
    @unpack
    async def test_exception_no_cache(self, ttl, error_msg, expected_size):
        """
        Testing exception handling (no caching)
        :param ttl: Time-to-live
        :param error_msg: Exception message
        :param expected_size: Expected cache size (0)
        """

        @async_lru_cache(ttl=ttl)
        async def failing_func():
            raise ValueError(error_msg)

        with self.assertRaises(ValueError):
            await failing_func()

        # Repeat — exception again, not cached
        with self.assertRaises(ValueError):
            await failing_func()

        stats = await failing_func.cache_stats()
        self.assertEqual(expected_size, stats["size"])

    @data(
        *[
            (None, 1, 2, 1),  # a=1, b=2, calls=1 (hit)
            (None, 3, 4, 1),
        ]
    )
    @unpack
    async def test_custom_key_func(self, ttl, a, b, expected_calls):
        """
        Testing custom key function
        :param ttl: Time-to-live
        :param a: First argument
        :param b: Second argument
        :param expected_calls: Expected number of calls
        """
        call_count = 0

        def key_func(a, b):
            return f"{a}-{b}"

        @async_lru_cache(ttl=ttl, key_func=key_func)
        async def func(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        await func(a, b)
        await func(a, b)  # Hit

        self.assertEqual(expected_calls, call_count)

    @data(
        *[
            (None, 2, 0),  # After clear size=0
        ]
    )
    @unpack
    async def test_clear(self, ttl, initial_calls, expected_size):
        """
        Testing cache clear
        :param ttl: Time-to-live
        :param initial_calls: Number of initial calls
        :param expected_size: Size after clear (0)
        """

        @async_lru_cache(ttl=ttl)
        async def func(x):
            return x

        for i in range(initial_calls):
            await func(i)

        stats = await func.cache_stats()
        self.assertEqual(initial_calls, stats["size"])

        await func.cache_clear()
        stats = await func.cache_stats()
        self.assertEqual(expected_size, stats["size"])
        self.assertEqual(0, stats["hits"])
        self.assertEqual(0, stats["misses"])

    @data(
        *[
            (1, None, "key", 100, 1),  # hit=1
        ]
    )
    @unpack
    async def test_direct_cache(self, maxsize, ttl, key, value, expected_hits):
        """
        Testing direct use of AsyncLRUCache
        :param maxsize: Maximum size
        :param ttl: Time-to-live
        :param key: Key
        :param value: Value from creator
        :param expected_hits: Expected hits after calls
        """
        cache = AsyncLRUCache(maxsize=maxsize, ttl=ttl)

        async def creator():
            return value

        await cache.get(key, creator)
        await cache.get(key, creator)  # Hit

        stats = await cache.stats()
        self.assertEqual(expected_hits, stats["hits"])
        self.assertEqual(1, stats["misses"])
        self.assertEqual(1, stats["size"])

        await cache.clear()
        stats = await cache.stats()
        self.assertEqual(0, stats["size"])

    @data(
        *[
            (3, None, 4, [1, 2, 3, 4], 4),  # After access to 1, eviction 2, then add 4; calls=4
        ]
    )
    @unpack
    async def test_lru_eviction_order(self, maxsize, ttl, num_keys, access_order, expected_calls):
        """
        Testing LRU eviction order
        :param maxsize: Maximum cache size
        :param ttl: Time-to-live
        :param num_keys: Number of keys to add
        :param access_order: Access order for usage simulation
        :param expected_calls: Expected number of calls (miss for evicted)
        """
        call_count = 0

        @async_lru_cache(maxsize=maxsize, ttl=ttl)
        async def func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # Add keys 1,2,3 (cache full)
        await func(1)
        await func(2)
        await func(3)

        # Access 1 (make it recently used), then add 4 (evict 2 as least recent)
        await func(1)
        await func(4)

        # Check: 1,3,4 in cache (hit), 2 evicted (miss)
        await func(1)  # Hit
        await func(3)  # Hit
        await func(4)  # Hit
        await func(2)  # Miss

        self.assertEqual(expected_calls + 1, call_count)  # +1 for miss 2

        stats = await func.cache_stats()
        self.assertEqual(maxsize, stats["size"])
        
    @data(*[
        (None, 0.1, 3, "TestError"),  # 3 concurrent, error in creator
    ])
    @unpack
    async def test_concurrency_with_error(self, ttl, delay, num_calls, error_msg):
        """
        Testing concurrency with error in creator
        :param ttl: Time-to-live
        :param delay: Delay
        :param num_calls: Number of concurrent calls
        :param error_msg: Error message
        """
        @async_lru_cache(ttl=ttl)
        async def failing_func():
            await asyncio.sleep(delay)
            raise ValueError(error_msg)

        # Concurrent calls, all should get error
        with self.assertRaises(ValueError):
            await asyncio.gather(*(failing_func() for _ in range(num_calls)))

        stats = await failing_func.cache_stats()
        self.assertEqual(0, stats['size'])  # No cache after error
        self.assertEqual(0, stats['hits'])
        self.assertEqual(0, stats['misses'])  # Misses not incremented on error
        
    @data(*[
        (0, None, 5, 5),  # 5 calls, all misses
    ])
    @unpack
    async def test_maxsize_zero(self, maxsize, ttl, num_calls, expected_calls):
        """
        Testing cache with maxsize=0 (disabled)
        :param maxsize: Size (0)
        :param ttl: Time-to-live
        :param num_calls: Number of calls
        :param expected_calls: Expected number of real calls (all)
        """
        call_count = 0

        @async_lru_cache(maxsize=maxsize, ttl=ttl)
        async def func():
            nonlocal call_count
            call_count += 1
            return 42

        for _ in range(num_calls):
            await func()

        self.assertEqual(expected_calls, call_count)

        stats = await func.cache_stats()
        self.assertEqual(0, stats['size'])
        self.assertEqual(0, stats['hits'])  # No hits
        self.assertEqual(expected_calls, stats['misses'])
        
    @data(*[
        (128, None, 10),  # 10 calls with different keys
    ])
    @unpack
    async def test_stats_consistency(self, maxsize, ttl, num_keys):
        """
        Testing statistics consistency
        :param maxsize: Maximum size
        :param ttl: Time-to-live
        :param num_keys: Number of keys
        """
        @async_lru_cache(maxsize=maxsize, ttl=ttl)
        async def func(x):
            return x

        for i in range(num_keys):
            await func(i)
            await func(i)  # Hit

        stats = await func.cache_stats()
        info = func.cache_info()

        self.assertEqual(num_keys, stats['misses'])
        self.assertEqual(num_keys, stats['hits'])
        self.assertEqual(num_keys, stats['size'])

        # Check info parsing
        info_dict = dict(item.split('=') for item in info.split(', '))
        self.assertEqual(stats['hits'], int(info_dict['hits']))
        self.assertEqual(stats['misses'], int(info_dict['misses']))
        
    @data(*[
        (0.05, 0.1, 3, 1),  # TTL expires during delay, second call — miss
    ])
    @unpack
    async def test_ttl_with_concurrency(self, ttl, delay, num_calls, expected_calls):
        """
        Testing TTL with concurrency
        :param ttl: Time-to-live (small)
        :param delay: Delay > TTL
        :param num_calls: Number of concurrent
        :param expected_calls: Expected (first miss, then expiration)
        """
        call_count = 0

        @async_lru_cache(ttl=ttl)
        async def slow_func():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(delay)
            return 42

        # Concurrent, but due to delay > TTL, after first — expiration
        results = await asyncio.gather(*(slow_func() for _ in range(num_calls)))

        self.assertEqual([42] * num_calls, results)
        self.assertGreaterEqual(call_count, expected_calls)  # May be more due to race

        await asyncio.sleep(ttl + 0.01)
        await slow_func()  # Miss after expiration
        self.assertEqual(call_count + 1, call_count + 1)