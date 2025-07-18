
# async-lru-ttl-cache

Asynchronous LRU cache with TTL support for Python. Supports concurrent requests without duplicating calls.

## Installation

Install via pip:

```bash
pip install async-lru-ttl-cache
```

## Usage

### Decorator

```python
from async_lru_ttl_cache import async_lru_cache

@async_lru_cache(maxsize=128, ttl=60)
async def expensive_func(arg1, arg2):
    await asyncio.sleep(1)
    return arg1 + arg2

result = await expensive_func(1, 2)  # Computed
result2 = await expensive_func(1, 2)  # Cached
```

### Direct Class Usage

```python
from async_lru_ttl_cache import AsyncLRUCache

cache = AsyncLRUCache(maxsize=10, ttl=30)

async def get_value(key):
    return await cache.get(key, lambda: await some_async_func())
```

### Cache Management

- `await cache.clear()`: Clear cache.
- `await cache.stats()`: Get {'hits': int, 'misses': int, 'size': int}.
- `cache.cache_info()`: String with stats.

For methods, cache is per-instance.

## Tests

Run tests with `unittest`:

```bash
python -m unittest discover tests
```

Requires `ddt` for data-driven tests: `pip install ddt`.
