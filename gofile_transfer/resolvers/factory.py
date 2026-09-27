"""Resolver Factory for selecting appropriate link resolver."""

from typing import List
from .base import BaseResolver, ResolvedURL
from .gdrive import GoogleDriveResolver
from .sourceforge import SourceForgeResolver
from .mediafire import MediaFireResolver
from .gofile import GoFileResolver
from .direct import DirectURLResolver


class ResolverFactory:
    """Factory to register and resolve URLs using suitable resolvers."""

    def __init__(self):
        self.resolvers: List[BaseResolver] = [
            GoogleDriveResolver(),
            SourceForgeResolver(),
            MediaFireResolver(),
            GoFileResolver(),
            DirectURLResolver(),  # Fallback resolver for direct links & Dropbox
        ]

    def resolve(self, url: str) -> ResolvedURL:
        """Find the matching resolver for the URL and resolve it."""
        for resolver in self.resolvers:
            if resolver.can_handle(url):
                return resolver.resolve(url)
        raise ValueError(f"No resolver capable of handling URL: {url}")
