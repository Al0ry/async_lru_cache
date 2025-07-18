
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

### Custom Key Function
You can provide a custom key_func to generate cache keys from function arguments. The key_func receives the arguments of the decorated function (excluding self for methods) and must return a hashable value (e.g., a tuple).

Example with a custom key function that ignores one argument:
```
from typing import Tuple
from async_lru_ttl_cache import async_lru_cache

def key_func(ignore_arg: str, version: int) -> Tuple[int]:
    """
    Generates a cache key, ignoring the first argument.

    Args:
        ignore_arg: Argument to ignore (e.g., some context).
        version: Version to use in the key.

    Returns:
        Tuple for the cache key.
    """
    return (version,)

@async_lru_cache(key_func=key_func)
async def get_cached_data(ignore_arg: str, version: int) -> int:
    await asyncio.sleep(1)
    return version * 10

# Usage
result = await get_cached_data("context1", 42)  # Computed
result2 = await get_cached_data("context2", 42)  # Cached (ignores ignore_arg)
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
