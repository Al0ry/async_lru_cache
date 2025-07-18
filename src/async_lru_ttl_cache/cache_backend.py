from abc import ABC, abstractmethod
from typing import Any, Hashable, Optional

__all__ = ["CacheBackendBase"]

class CacheBackendBase(ABC):
    """Abstract base class for cache backends."""
    
    @abstractmethod
    async def get(self, key: Hashable) -> Optional[tuple[Any, float]]:
        pass
    
    @abstractmethod
    async def set(self, key: Hashable, value: tuple[Any, float]) -> None:
        pass
    
    @abstractmethod
    async def delete(self, key: Hashable) -> None:
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        pass
    
    @abstractmethod
    async def size(self) -> int:
        pass
    
    @abstractmethod
    def move_to_end(self, key: Hashable) -> None:
        pass