from base_tests import BaseTestsAsyncLRUCache  # Импорт базового класса

class TestsMemoryAsyncLRUCache(BaseTestsAsyncLRUCache):
    backend = 'memory'
    extra_kwargs = {}