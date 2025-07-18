import asyncio
import pickle
import os

from collections import OrderedDict
from typing import Any, Optional, Hashable

from async_lru_ttl_cache.cache_backend import CacheBackendBase


class DiskBackend(CacheBackendBase):
    """Disk-based cache backend using pickle for persistence."""

    def __init__(self, maxsize: int, cache_dir: str = ".cache", namespace: Optional[str] = None):
        self._maxsize = maxsize
        self._cache_dir = cache_dir
        self._namespace = namespace
        self._cache: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()
        self._lock = asyncio.Lock()
        os.makedirs(cache_dir, exist_ok=True)
        self._load_cache()

    def _get_filename(self, key: Hashable) -> str:
        h = hash(key)
        if self._namespace:
            return os.path.join(self._cache_dir, f"cache_{self._namespace}_{h}")
        return os.path.join(self._cache_dir, f"cache_{h}")

    def _load_cache(self):
        """Load cache from disk."""
        prefix = f"cache_{self._namespace}_" if self._namespace else "cache_"
        for filename in os.listdir(self._cache_dir):
            if not filename.startswith(prefix):
                continue
            try:
                with open(os.path.join(self._cache_dir, filename), "rb") as f:
                    key, value = pickle.load(f)
                    self._cache[key] = value
            except Exception:
                continue

    async def _save_item(self, key: Hashable, value: tuple[Any, float]):
        """Save single item to disk."""
        try:
            filename = self._get_filename(key)
            with open(filename, "wb") as f:
                pickle.dump((key, value), f)
        except Exception:
            pass

    async def get(self, key: Hashable) -> Optional[tuple[Any, float]]:
        async with self._lock:
            return self._cache.get(key)

    async def set(self, key: Hashable, value: tuple[Any, float]) -> None:
        if self._maxsize == 0:
            return
        async with self._lock:
            self._cache[key] = value
            await self._save_item(key, value)
            if len(self._cache) > self._maxsize:
                old_key, _ = self._cache.popitem(last=False)
                try:
                    os.remove(self._get_filename(old_key))
                except FileNotFoundError:
                    pass

    async def delete(self, key: Hashable) -> None:
        async with self._lock:
            self._cache.pop(key, None)
            try:
                os.remove(self._get_filename(key))
            except FileNotFoundError:
                pass

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
            prefix = f"cache_{self._namespace}_" if self._namespace else "cache_"
            for filename in os.listdir(self._cache_dir):
                if filename.startswith(prefix):
                    try:
                        os.remove(os.path.join(self._cache_dir, filename))
                    except Exception:
                        continue

    async def size(self) -> int:
        async with self._lock:
            return len(self._cache)

    def move_to_end(self, key: Hashable) -> None:
        self._cache.move_to_end(key)
