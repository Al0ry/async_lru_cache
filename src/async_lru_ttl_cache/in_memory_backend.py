from typing import Any, Optional, Hashable
from collections import OrderedDict

from async_lru_ttl_cache.cache_backend import CacheBackendBase

class InMemoryBackend(CacheBackendBase):
    """In-memory cache backend using OrderedDict."""
    
    def __init__(self, maxsize: int):
        self._cache: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()
        self._maxsize = maxsize
    
    async def get(self, key: Hashable) -> Optional[tuple[Any, float]]:
        return self._cache.get(key)
    
    async def set(self, key: Hashable, value: tuple[Any, float]) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)
    
    async def delete(self, key: Hashable) -> None:
        self._cache.pop(key, None)
    
    async def clear(self) -> None:
        self._cache.clear()
    
    async def size(self) -> int:
        return len(self._cache)
    
    def move_to_end(self, key: Hashable) -> None:
        self._cache.move_to_end(key)