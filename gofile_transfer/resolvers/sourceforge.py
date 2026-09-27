"""SourceForge URL resolver with signed redirect chain extraction."""

import re
import urllib.parse
from typing import Optional
from .base import BaseResolver, ResolvedURL

try:
    import httpx
except ImportError:
    httpx = None
import requests


class SourceForgeResolver(BaseResolver):
    """Resolver for SourceForge project files using signed redirect chain extraction."""

    def can_handle(self, url: str) -> bool:
        return "sourceforge.net" in url.lower()

    def resolve(self, url: str) -> ResolvedURL:
        cleaned_url = url.strip().strip("'\"")
        
        # Ensure /download suffix on project file links
        if not cleaned_url.endswith("/download") and "/files/" in cleaned_url:
            if not cleaned_url.endswith("/"):
                cleaned_url += "/download"
            else:
                cleaned_url += "download"

        headers = {"User-Agent": "Wget/1.21.3"}

        # Follow redirect chain with Wget user-agent to get direct signed mirror CDN URL
        if httpx is not None:
            with httpx.Client(follow_redirects=True, timeout=45.0) as client:
                resp = client.head(cleaned_url, headers=headers)
                if resp.status_code >= 400 or "content-length" not in resp.headers:
                    resp = client.get(cleaned_url, headers=headers)

                direct_url = str(resp.url)
                file_size = int(resp.headers.get("Content-Length", 0)) or None
                cd = resp.headers.get("Content-Disposition", "")
        else:
            with requests.Session() as s:
                resp = s.head(cleaned_url, headers=headers, allow_redirects=True, timeout=45)
                if resp.status_code >= 400 or "content-length" not in resp.headers:
                    resp = s.get(cleaned_url, headers=headers, stream=True, allow_redirects=True, timeout=45)
                direct_url = str(resp.url)
                file_size = int(resp.headers.get("Content-Length", 0)) or None
                cd = resp.headers.get("Content-Disposition", "")

        filename = None
        if "filename=" in cd:
            fname_match = re.search(r'filename="?([^";]+)"?', cd)
            if fname_match:
                filename = fname_match.group(1)

        if not filename:
            parsed = urllib.parse.urlparse(direct_url)
            path_part = parsed.path.rstrip("/")
            if path_part:
                filename = path_part.split("/")[-1]

        if not filename or filename == "download":
            parsed = urllib.parse.urlparse(cleaned_url.replace("/download", ""))
            filename = parsed.path.split("/")[-1]

        return ResolvedURL(
            direct_url=direct_url,
            filename=filename,
            file_size=file_size,
            headers=headers,
            supports_ranges=True,
            mirror_urls=[direct_url]
        )
