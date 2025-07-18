from typing import Any, Callable, Optional, Hashable
import time
import functools
import inspect
import asyncio
from collections import OrderedDict


__all__ = [
    "async_lru_cache",
    "AsyncLRUCache",
]


class AsyncLRUCache:
    """Simple asynchronous LRU cache implementation with TTL support.

    This class provides a cache with limited size and optional time-to-live (TTL).
    Supports concurrent requests without duplicating calls to the creator function.

    Arguments:
        maxsize: Maximum cache size (default 128).
        ttl: Time-to-live for items in seconds (None for infinite).

    Example usage:
        cache = AsyncLRUCache(maxsize=10, ttl=60)
        async def get_value(key):
            return await cache.get(key, lambda: await asyncio.sleep(1) or 'value')
    """

    def __init__(self, maxsize: int = 128, ttl: Optional[float] = None) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()
        self._pending: dict[Hashable, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: Hashable, creator: Callable[[], Any]) -> Any:
        if key in self._cache:
            async with self._lock:
                if key in self._cache:
                    value, ts = self._cache[key]
                    if self._ttl is not None and time.monotonic() - ts > self._ttl:
                        del self._cache[key]
                    else:
                        self._cache.move_to_end(key)
                        self._hits += 1
                        return value

        pending_fut = None
        fut = None
        async with self._lock:
            if key in self._pending:
                pending_fut = self._pending[key]
            else:
                fut = asyncio.Future()
                self._pending[key] = fut
                pending_fut = fut

        if fut is not None:
            try:
                value = await creator()
            except Exception as exc:
                async with self._lock:
                    if self._pending.get(key) is fut:
                        del self._pending[key]
                fut.set_exception(exc)
                raise
            else:
                async with self._lock:
                    if self._pending.get(key) is fut:
                        del self._pending[key]
                    if key in self._cache:
                        cached_value, cached_ts = self._cache[key]
                        if self._ttl is None or time.monotonic() - cached_ts <= self._ttl:
                            self._cache.move_to_end(key)
                            self._hits += 1
                            fut.set_result(cached_value)
                            return cached_value

                    self._cache[key] = (value, time.monotonic())
                    self._cache.move_to_end(key)
                    self._misses += 1
                    if len(self._cache) > self._maxsize:
                        self._cache.popitem(last=False)
                    fut.set_result(value)
                    return value
        else:
            try:
                value = await pending_fut
            except Exception:
                raise
            async with self._lock:
                if key in self._cache:
                    value, ts = self._cache[key]
                    if self._ttl is not None and time.monotonic() - ts > self._ttl:
                        del self._cache[key]
                    else:
                        self._cache.move_to_end(key)
                        self._hits += 1
                        return value
            return value

    async def clear(self) -> None:
        """Clears the cache and cancels pending tasks.

        Example:
            await cache.clear()  # All data removed, statistics reset.
        """
        async with self._lock:
            self._cache.clear()
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(RuntimeError("Cache cleared"))
            self._pending.clear()
            self._hits = 0
            self._misses = 0

    async def stats(self) -> dict[str, int]:
        """Returns cache statistics under lock.

        Example:
            stats = await cache.stats()  # {'hits': 5, 'misses': 3, 'size': 4}
        """
        async with self._lock:
            return {"hits": self._hits, "misses": self._misses, "size": len(self._cache)}

    def cache_info(self) -> str:
        """Returns cache information without lock.

        Example:
            info = cache.cache_info()  # 'hits=5, misses=3, maxsize=128, currsize=4'
        """
        return f"hits={self._hits}, misses={self._misses}, maxsize={self._maxsize}, currsize={len(self._cache)}"


def async_lru_cache(
    maxsize: int = 128,
    ttl: Optional[float] = None,
    key_func: Optional[Callable[..., Hashable]] = None,
):
    """
    Decorator for asynchronous LRU cache with TTL and optional key generation function.

    :param maxsize: Maximum cache size.
    :param ttl: Time-to-live for items in seconds (None for infinite).
    :param key_func: Optional function to generate key from *args, **kwargs.
                     If None, uses default hashable combination of arguments.
                     key_func should accept function arguments without self (for methods).

    Example usage:
        @async_lru_cache(maxsize=5, ttl=30)
        async def expensive_func(arg1, arg2):
            await asyncio.sleep(1)
            return arg1 + arg2

        result = await expensive_func(1, 2)  # Computed
        result2 = await expensive_func(1, 2)  # From cache
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        is_method = list(inspect.signature(func).parameters.keys())[0] == "self" if inspect.signature(func).parameters else False

        cache_attr = f"_lru_cache_{func.__name__}"

        if key_func is None:

            def default_key_func(*args, **kwargs):
                return (tuple(args), tuple(sorted(kwargs.items())))

            _key_func = default_key_func
        else:
            _key_func = key_func

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if is_method:
                instance = args[0]
                if not hasattr(instance, cache_attr):
                    setattr(instance, cache_attr, AsyncLRUCache(maxsize=maxsize, ttl=ttl))
                cache = getattr(instance, cache_attr)
                key_args = args[1:]
            else:
                if not hasattr(wrapper, "_cache"):
                    setattr(wrapper, "_cache", AsyncLRUCache(maxsize=maxsize, ttl=ttl))
                cache = getattr(wrapper, "_cache")
                key_args = args

            key = _key_func(*key_args, **kwargs)

            async def creator() -> Any:
                return await func(*args, **kwargs)

            return await cache.get(key, creator)

        def get_cache(instance=None):
            if is_method:
                if instance is None:
                    raise ValueError("For methods, provide instance to access cache")
                return getattr(instance, cache_attr)
            else:
                return wrapper._cache

        async def cache_clear(instance=None):
            cache = get_cache(instance)
            await cache.clear()

        async def cache_stats(instance=None):
            cache = get_cache(instance)
            return await cache.stats()

        def cache_info(instance=None):
            cache = get_cache(instance)
            return cache.cache_info()

        wrapper.cache_clear = cache_clear
        wrapper.cache_stats = cache_stats
        wrapper.cache_info = cache_info

        return wrapper

    return decorator
