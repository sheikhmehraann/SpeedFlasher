"""Resolvers package."""

from .base import BaseResolver, ResolvedURL
from .gdrive import GoogleDriveResolver
from .sourceforge import SourceForgeResolver
from .mediafire import MediaFireResolver
from .gofile import GoFileResolver
from .direct import DirectURLResolver
from .factory import ResolverFactory

__all__ = [
    "BaseResolver",
    "ResolvedURL",
    "GoogleDriveResolver",
    "SourceForgeResolver",
    "MediaFireResolver",
    "GoFileResolver",
    "DirectURLResolver",
    "ResolverFactory",
]
