import asyncio
import pickle

from typing import Any, Optional, Hashable
from async_lru_ttl_cache.cache_backend import CacheBackendBase

try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class RedisBackend(CacheBackendBase):
    """Redis-based cache backend for distributed caching."""

    def __init__(self, maxsize: int, redis_url: str = "redis://localhost:6379/0", namespace: Optional[str] = None):
        if redis is None:
            raise ImportError("redis.asyncio is required for RedisBackend")
        self._maxsize = maxsize
        self._redis = redis.from_url(redis_url)
        self._namespace = namespace
        self._lock = asyncio.Lock()
        self._lru_list = f"lru:{namespace}" if namespace else "lru_cache_list"

    def _get_actual_key(self, key: Hashable) -> str:
        skey = str(key)
        return f"{self._namespace}:{skey}" if self._namespace else skey

    async def get(self, key: Hashable) -> Optional[tuple[Any, float]]:
        actual_key = self._get_actual_key(key)
        async with self._lock:
            value = await self._redis.get(actual_key)
            if value:
                await self._redis.lrem(self._lru_list, 0, actual_key)
                await self._redis.rpush(self._lru_list, actual_key)
                return pickle.loads(value)
            return None

    async def set(self, key: Hashable, value: tuple[Any, float]) -> None:
        if self._maxsize == 0:
            return
        actual_key = self._get_actual_key(key)
        async with self._lock:
            await self._redis.set(actual_key, pickle.dumps(value))
            await self._redis.rpush(self._lru_list, actual_key)
            size = await self._redis.llen(self._lru_list)
            if size > self._maxsize:
                old_key = await self._redis.lpop(self._lru_list)
                await self._redis.delete(old_key)

    async def delete(self, key: Hashable) -> None:
        actual_key = self._get_actual_key(key)
        async with self._lock:
            await self._redis.delete(actual_key)
            await self._redis.lrem(self._lru_list, 0, actual_key)

    async def clear(self) -> None:
        async with self._lock:
            keys = await self._redis.lrange(self._lru_list, 0, -1)
            if keys:
                await self._redis.delete(*keys)
            await self._redis.delete(self._lru_list)

    async def size(self) -> int:
        async with self._lock:
            return await self._redis.llen(self._lru_list)

    def move_to_end(self, key: Hashable) -> None:
        pass  # Handled in get/set for Redis
