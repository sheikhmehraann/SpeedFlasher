"""MediaFire link resolver."""

import re
import requests
from urllib.parse import urlparse
from .base import BaseResolver, ResolvedURL


class MediaFireResolver(BaseResolver):
    """Resolver for MediaFire file sharing links."""

    MEDIAFIRE_DOMAINS = ["mediafire.com", "www.mediafire.com"]

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return any(domain in parsed.netloc for domain in self.MEDIAFIRE_DOMAINS)

    def resolve(self, url: str) -> ResolvedURL:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

        session = requests.Session()
        res = session.get(url, headers=headers, timeout=15)
        res.raise_for_status()

        html = res.text
        direct_url = None

        # Pattern 1: id="downloadButton" href="..."
        match = re.search(r'id=["\']downloadButton["\'][^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if match:
            direct_url = match.group(1)

        # Pattern 2: aria-label="Download file" href="..."
        if not direct_url:
            match = re.search(r'aria-label=["\']Download file["\'][^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if match:
                direct_url = match.group(1)

        # Pattern 3: direct download link pattern (download*.mediafire.com)
        if not direct_url:
            match = re.search(r'https?://download\d*\.mediafire\.com/[^\s"\'<>]+', html)
            if match:
                direct_url = match.group(0)

        if not direct_url:
            raise ValueError(f"Could not parse MediaFire direct download link from: {url}")

        # Probe headers of direct URL
        head_res = session.head(direct_url, headers=headers, allow_redirects=True, timeout=15)

        filename = None
        cd = head_res.headers.get("Content-Disposition", "")
        if cd:
            fn_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', cd, re.IGNORECASE)
            if fn_match:
                filename = fn_match.group(1)

        if not filename:
            path_parts = [p for p in urlparse(direct_url).path.split("/") if p]
            filename = path_parts[-1] if path_parts else "mediafire_file.bin"

        file_size = None
        if "Content-Length" in head_res.headers:
            try:
                file_size = int(head_res.headers["Content-Length"])
            except ValueError:
                pass

        supports_ranges = head_res.headers.get("Accept-Ranges") == "bytes"

        return ResolvedURL(
            original_url=url,
            direct_url=direct_url,
            filename=filename,
            file_size=file_size,
            headers=headers,
            cookies=session.cookies.get_dict(),
            supports_ranges=supports_ranges
        )
