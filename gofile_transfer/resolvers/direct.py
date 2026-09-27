"""Direct HTTP/HTTPS link resolver with smart share link conversion (Dropbox, Mediafire)."""

import re
import requests
from urllib.parse import urlparse, unquote
from .base import BaseResolver, ResolvedURL


class DirectURLResolver(BaseResolver):
    """Fallback resolver for generic direct HTTP/HTTPS download URLs."""

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in ["http", "https"]

    def _convert_known_share_links(self, url: str) -> str:
        """Convert known file sharing site links into direct download links."""
        # Dropbox: dl=0 -> dl=1
        if "dropbox.com" in url:
            if "dl=0" in url:
                return url.replace("dl=0", "dl=1")
            elif "dl=1" not in url:
                delimiter = "&" if "?" in url else "?"
                return f"{url}{delimiter}dl=1"

        # GitHub Releases / raw links
        if "github.com" in url and "/blob/" in url:
            return url.replace("/blob/", "/raw/")

        return url

    def resolve(self, url: str) -> ResolvedURL:
        direct_target = self._convert_known_share_links(url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            res = requests.head(direct_target, headers=headers, allow_redirects=True, timeout=15)
            if res.status_code >= 400 or "Content-Type" in res.headers and "text/html" in res.headers.get("Content-Type", ""):
                res = requests.get(direct_target, headers=headers, allow_redirects=True, stream=True, timeout=15)
        except Exception:
            res = requests.get(direct_target, headers=headers, allow_redirects=True, stream=True, timeout=15)

        final_url = res.url
        filename = None
        cd = res.headers.get("Content-Disposition", "")
        if cd:
            fn_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', cd, re.IGNORECASE)
            if fn_match:
                filename = fn_match.group(1)

        if not filename:
            path = urlparse(final_url).path
            filename = unquote(path.split("/")[-1]) if path and path != "/" else "downloaded_file.bin"

        if not filename or filename == "/":
            filename = "downloaded_file.bin"

        file_size = None
        if "Content-Length" in res.headers:
            try:
                file_size = int(res.headers["Content-Length"])
            except ValueError:
                pass

        supports_ranges = res.headers.get("Accept-Ranges") == "bytes"

        return ResolvedURL(
            original_url=url,
            direct_url=final_url,
            filename=filename,
            file_size=file_size,
            headers=headers,
            cookies=res.cookies.get_dict(),
            supports_ranges=supports_ranges
        )
