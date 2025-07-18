import time
import functools
import inspect
import asyncio

from typing import Any, Callable, Optional, Hashable
import uuid

from async_lru_ttl_cache.disk_backend import DiskBackend
from async_lru_ttl_cache.in_memory_backend import InMemoryBackend
from async_lru_ttl_cache.redis_backend import RedisBackend

__all__ = [
    "async_lru_cache",
    "AsyncLRUCache",
]


class AsyncLRUCache:
    """Simple asynchronous LRU cache implementation with TTL support and multiple backends.

    Arguments:
        maxsize: Maximum cache size (default 128).
        ttl: Time-to-live for items in seconds (None for infinite).
        backend: Cache backend type ('memory', 'disk', 'redis').
        cache_dir: Directory for disk backend (default '.cache').
        redis_url: Redis connection URL (default 'redis://localhost:6379/0').
        namespace: Optional namespace for key isolation in persistent backends (auto-generated UUID if None).

    Example usage:
        cache = AsyncLRUCache(maxsize=10, ttl=60, backend='disk', cache_dir='.cache', namespace='my_cache')
        async def get_value(key):
            return await cache.get(key, lambda: await asyncio.sleep(1) or 'value')
    """

    def __init__(self, maxsize: int = 128, ttl: Optional[float] = None, 
                 backend: str = 'memory', cache_dir: str = '.cache', 
                 redis_url: str = 'redis://localhost:6379/0', namespace: Optional[str] = None) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._namespace = namespace if namespace is not None else str(uuid.uuid4())
        if backend == 'memory':
            self._backend = InMemoryBackend(maxsize)
        elif backend == 'disk':
            self._backend = DiskBackend(maxsize, cache_dir, self._namespace)
        elif backend == 'redis':
            self._backend = RedisBackend(maxsize, redis_url, self._namespace)
        else:
            raise ValueError("Unsupported backend. Use 'memory', 'disk', or 'redis'.")
        self._pending: dict[Hashable, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: Hashable, creator: Callable[[], Any]) -> Any:
        cached = await self._backend.get(key)
        if cached:
            async with self._lock:
                value, ts = cached
                if self._ttl is not None and time.monotonic() - ts > self._ttl:
                    await self._backend.delete(key)
                else:
                    if self._maxsize > 0:
                        self._backend.move_to_end(key)
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
                    cached = await self._backend.get(key)
                    if cached:
                        cached_value, cached_ts = cached
                        if self._ttl is None or time.monotonic() - cached_ts <= self._ttl:
                            if self._maxsize > 0:
                                self._backend.move_to_end(key)
                            self._hits += 1
                            fut.set_result(cached_value)
                            return cached_value

                    self._misses += 1
                    if self._maxsize > 0:
                        await self._backend.set(key, (value, time.monotonic()))
                        self._backend.move_to_end(key)
                    fut.set_result(value)
                    return value
        else:
            try:
                value = await pending_fut
            except Exception:
                raise
            async with self._lock:
                cached = await self._backend.get(key)
                if cached:
                    value, ts = cached
                    if self._ttl is not None and time.monotonic() - ts > self._ttl:
                        await self._backend.delete(key)
                    else:
                        if self._maxsize > 0:
                            self._backend.move_to_end(key)
                        self._hits += 1
                        return value
            return value

    async def clear(self) -> None:
        """Clears the cache and cancels pending tasks."""
        async with self._lock:
            await self._backend.clear()
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(RuntimeError("Cache cleared"))
            self._pending.clear()
            self._hits = 0
            self._misses = 0

    async def stats(self) -> dict[str, int]:
        """Returns cache statistics under lock."""
        async with self._lock:
            return {"hits": self._hits, "misses": self._misses, "size": await self._backend.size()}

    async def cache_info(self) -> str:
        """Returns cache information."""
        return f"hits={self._hits}, misses={self._misses}, maxsize={self._maxsize}, currsize={await self._backend.size()}"

def async_lru_cache(
    maxsize: int = 128,
    ttl: Optional[float] = None,
    key_func: Optional[Callable[..., Hashable]] = None,
    backend: str = 'memory',
    cache_dir: str = '.cache',
    redis_url: str = 'redis://localhost:6379/0',
    namespace: Optional[str] = None,
):
    """
    Decorator for asynchronous LRU cache with TTL and multiple backends.

    :param maxsize: Maximum cache size.
    :param ttl: Time-to-live for items in seconds (None for infinite).
    :param key_func: Optional function to generate key from *args, **kwargs.
    :param backend: Cache backend type ('memory', 'disk', 'redis').
    :param cache_dir: Directory for disk backend.
    :param redis_url: Redis connection URL.
    :param namespace: Optional namespace for key isolation.

    Example usage:
        @async_lru_cache(maxsize=5, ttl=30, backend='redis', redis_url='redis://localhost:6379/0', namespace='my_namespace')
        async def expensive_func(arg1, arg2):
            await asyncio.sleep(1)
            return arg1 + arg2
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
                    setattr(instance, cache_attr, AsyncLRUCache(maxsize=maxsize, ttl=ttl, backend=backend, 
                                                              cache_dir=cache_dir, redis_url=redis_url, namespace=namespace))
                cache = getattr(instance, cache_attr)
                key_args = args[1:]
            else:
                if not hasattr(wrapper, "_cache"):
                    setattr(wrapper, "_cache", AsyncLRUCache(maxsize=maxsize, ttl=ttl, backend=backend, 
                                                           cache_dir=cache_dir, redis_url=redis_url, namespace=namespace))
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

        async def cache_info(instance=None):
            cache = get_cache(instance)
            return await cache.cache_info()

        wrapper.cache_clear = cache_clear
        wrapper.cache_stats = cache_stats
        wrapper.cache_info = cache_info

        return wrapper

    return decorator