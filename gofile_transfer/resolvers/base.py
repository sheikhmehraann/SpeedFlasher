"""Base class and common types for URL resolvers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, List


@dataclass
class ResolvedURL:
    """Dataclass holding resolved direct download information."""
    direct_url: str
    original_url: str = ""
    filename: Optional[str] = None
    file_size: Optional[int] = None
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    supports_ranges: bool = True
    mirror_urls: List[str] = field(default_factory=list)


class BaseResolver(ABC):
    """Abstract base class for all link resolvers."""

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this resolver can handle the given URL."""
        pass

    @abstractmethod
    def resolve(self, url: str) -> ResolvedURL:
        """Resolve given URL to a direct downloadable URL."""
        pass
