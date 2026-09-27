"""Google Drive link resolver with quota and error detection."""

import re
import os
import requests
import urllib.parse
from urllib.parse import parse_qs, urlparse, urljoin
from typing import Optional, Tuple
from .base import BaseResolver, ResolvedURL


class GoogleDriveResolver(BaseResolver):
    """Resolver for Google Drive links with quota-limit detection and token confirmation."""

    GDRIVE_DOMAINS = ["drive.google.com", "docs.google.com", "drive.usercontent.google.com"]

    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return any(domain in parsed.netloc for domain in self.GDRIVE_DOMAINS)

    def extract_file_id_and_resourcekey(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract Google Drive file ID and optional resourcekey from various URL patterns."""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        resourcekey = params.get("resourcekey", [None])[0]

        match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1), resourcekey

        if "id" in params and params["id"]:
            return params["id"][0], resourcekey

        match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1), resourcekey

        return None, resourcekey

    def extract_file_id(self, url: str) -> Optional[str]:
        file_id, _ = self.extract_file_id_and_resourcekey(url)
        return file_id

    def resolve(self, url: str) -> ResolvedURL:
        file_id, resourcekey = self.extract_file_id_and_resourcekey(url)
        if not file_id:
            raise ValueError(f"Could not extract Google Drive file ID from URL: {url}")

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        initial_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        if resourcekey:
            initial_url += f"&resourcekey={resourcekey}"
        res = session.get(initial_url, stream=True)

        final_res = res
        content_type = res.headers.get("Content-Type", "")

        if "text/html" in content_type:
            html_text = res.text

            # Check for Google Drive Quota / Rate Limit errors
            if "Too many users have viewed or downloaded this file recently" in html_text or "Quota exceeded" in html_text:
                raise RuntimeError(
                    "Google Drive download quota exceeded for this file. "
                    "Google has temporarily locked public downloads due to high traffic (24h limit). "
                    "Please try another link or make a copy in your Google Drive."
                )

            if "Access denied" in html_text or "You need access" in html_text or "accounts.google.com" in res.url:
                raise PermissionError(
                    "Google Drive access denied: This file is private or requires Google Account authorization. "
                    "Ensure link sharing is set to 'Anyone with the link'."
                )

            # Check for Google Drive "Download anyway" confirmation form
            soup = None
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_text, "html.parser")
            except Exception:
                pass

            form_params = {}
            action_url = None

            if soup:
                form = soup.find("form")
                if form:
                    action_url = form.get("action")
                    for inp in form.find_all("input"):
                        name = inp.get("name")
                        val = inp.get("value")
                        if name:
                            form_params[name] = val or ""
            else:
                form_match = re.search(r'<form[^>]*action="([^"]+)"[^>]*>(.*?)</form>', html_text, re.DOTALL | re.IGNORECASE)
                if form_match:
                    action_url = form_match.group(1)
                    form_content = form_match.group(2)
                    for input_tag in re.findall(r'<input\b[^>]*>', form_content, re.IGNORECASE):
                        name_m = re.search(r'name=["\']([^"\']+)["\']', input_tag)
                        val_m = re.search(r'value=["\']([^"\']*)["\']', input_tag)
                        if name_m:
                            form_params[name_m.group(1)] = val_m.group(1) if val_m else ""

            if action_url and form_params:
                if not action_url.startswith("http"):
                    action_url = urljoin(res.url, action_url)
                if "id" not in form_params:
                    form_params["id"] = file_id

                final_res = session.get(action_url, params=form_params, stream=True)

                # Re-verify that the response is actually a binary stream and not an HTML error
                if "text/html" in final_res.headers.get("Content-Type", ""):
                    if "Too many users" in final_res.text or "Quota exceeded" in final_res.text:
                        raise RuntimeError(
                            "\n❌ [Google Drive 24h Quota Exceeded]\n"
                            "Google Drive has temporarily locked public downloads for this file because too many users downloaded it recently.\n\n"
                            "💡 Quick Solutions to bypass this immediately:\n"
                            "  1. Upload the ROM zip/archive to https://gofile.io (Unlimited speed, no quotas) and pass the GoFile link.\n"
                            "  2. Or in Google Drive: Right-click the ROM file -> 'Make a copy' to your own Google Drive, set Link Sharing to 'Anyone with link', and use the new URL.\n"
                            "  3. Or use MediaFire / SourceForge / direct HTTP download link."
                        )
            else:
                # Check for confirm token in cookies or text
                confirm_token = None
                for key, val in session.cookies.items():
                    if key.startswith("download_warning"):
                        confirm_token = val
                        break

                if not confirm_token:
                    token_match = re.search(r'confirm=([a-zA-Z0-9_-]+)', html_text)
                    if token_match:
                        confirm_token = token_match.group(1)

                if confirm_token:
                    final_res = session.get(
                        "https://drive.google.com/uc?export=download",
                        params={"id": file_id, "confirm": confirm_token},
                        stream=True
                    )

        # Final validation: Ensure we do NOT treat small HTML error responses as files
        final_ct = final_res.headers.get("Content-Type", "")
        if "text/html" in final_ct and "Content-Disposition" not in final_res.headers:
            raise RuntimeError(
                "\n❌ [Google Drive Download Blocked]\n"
                "Google Drive served an HTML error page instead of the file stream.\n"
                "The file may be quota-locked, private, or deleted.\n"
                "Please verify the Google Drive link or upload the ROM to https://gofile.io or MediaFire."
            )

        filename = None
        cd = final_res.headers.get("Content-Disposition", "")
        if cd:
            fn_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', cd, re.IGNORECASE)
            if fn_match:
                filename = urllib.parse.unquote(fn_match.group(1).strip("\"'"))

        if not filename:
            filename = f"gdrive_{file_id}.bin"

        file_size = None
        if "Content-Length" in final_res.headers:
            try:
                file_size = int(final_res.headers["Content-Length"])
            except ValueError:
                pass

        supports_ranges = False

        return ResolvedURL(
            original_url=url,
            direct_url=final_res.url,
            filename=filename,
            file_size=file_size,
            headers=dict(final_res.request.headers),
            cookies=session.cookies.get_dict(),
            supports_ranges=supports_ranges
        )
