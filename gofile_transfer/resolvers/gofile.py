"""
⚡ gofile_transfer/resolvers/gofile.py - Ultra-Resilient GoFile.io URL Resolver ⚡
Integrates multi-tier TokenGenerator (WT), automated guest authentication,
and recursive folder parsing to deliver direct high-speed download links.
"""

import os
import re
import time
import json
import requests
from typing import Optional, Dict, Any, List
from urllib.parse import quote, urlparse

from .base import BaseResolver, ResolvedURL
from ..token_generator import token_generator, DEFAULT_USER_AGENT


class GoFileResolver(BaseResolver):
    """
    Production-grade link resolver for gofile.io files and folders.
    Bypasses GoFile anti-scraping and website token requirements.
    """

    API_BASE_URL = "https://api.gofile.io"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://gofile.io"
        })

    def can_handle(self, url: str) -> bool:
        """Check if URL points to a GoFile resource."""
        clean = url.lower()
        return "gofile.io" in clean or bool(re.search(r"gofile\.io/[dc]/", clean))

    @staticmethod
    def extract_content_id(url: str) -> str:
        """Extract alphanumeric content or folder ID from various GoFile URL formats."""
        url = url.strip().strip("\"'")
        match = re.search(r'gofile\.io/[dc]/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        match_query = re.search(r'gofile\.io/\?c=([a-zA-Z0-9_-]+)', url)
        if match_query:
            return match_query.group(1)
        match_raw = re.fullmatch(r'[a-zA-Z0-9_-]{5,36}', url)
        if match_raw:
            return url
        raise ValueError(f"Could not extract GoFile content ID from URL: {url}")

    def create_guest_token(self, retries: int = 3) -> str:
        """Create a temporary guest session token on GoFile."""
        url = f"{self.API_BASE_URL}/accounts"
        for attempt in range(1, retries + 1):
            try:
                res = self.session.post(
                    url,
                    json={},
                    headers={
                        "User-Agent": DEFAULT_USER_AGENT,
                        "Content-Type": "application/json",
                        "Origin": "https://gofile.io",
                        "Referer": "https://gofile.io/"
                    },
                    timeout=10
                )
                if res.status_code == 200:
                    data = res.json()
                    if data.get("status") == "ok":
                        token = data.get("data", {}).get("token")
                        if token:
                            return token
            except Exception:
                if attempt >= retries:
                    raise
                time.sleep(1.0)
        raise RuntimeError("Failed to obtain guest account token from GoFile API")

    def _get_account_token(self) -> str:
        """Retrieve token from environment GOFILE_TOKEN or create guest token."""
        env_token = os.environ.get("GOFILE_TOKEN", "").strip()
        if env_token and len(env_token) > 5:
            return env_token
        return self.create_guest_token()

    def fetch_content_data(self, content_id: str, token: str, retries: int = 3) -> Dict[str, Any]:
        """Fetch content metadata with dynamic WT token and auto-refresh on 401."""
        for attempt in range(1, retries + 1):
            wt = token_generator.generate_wt(token, retry_on_fail=(attempt > 1))
            
            headers = {
                "User-Agent": DEFAULT_USER_AGENT,
                "Authorization": f"Bearer {token}",
                "X-Website-Token": wt,
                "X-BL": "en-US",
                "Origin": "https://gofile.io",
                "Referer": f"https://gofile.io/d/{content_id}"
            }
            params = {
                "contentFilter": "",
                "page": "1",
                "pageSize": "1000",
                "sortField": "createTime",
                "sortDirection": "-1"
            }
            url = f"{self.API_BASE_URL}/contents/{quote(content_id)}"

            try:
                res = self.session.get(
                    url,
                    headers=headers,
                    params=params,
                    cookies={"accountToken": token},
                    timeout=15
                )
                if res.status_code == 401 or res.status_code == 403:
                    if attempt < retries:
                        token_generator.get_obf_js(force_refresh=True)
                        time.sleep(1.0)
                        continue
                    res.raise_for_status()

                res.raise_for_status()
                data = res.json()
                if data.get("status") != "ok":
                    if attempt < retries and "token" in str(data).lower():
                        token_generator.get_obf_js(force_refresh=True)
                        time.sleep(1.0)
                        continue
                    raise RuntimeError(f"GoFile API returned status '{data.get('status')}': {data}")

                return data.get("data", {})

            except requests.exceptions.RequestException as e:
                if attempt >= retries:
                    raise
                time.sleep(1.0)

        raise RuntimeError(f"Failed to fetch content data for GoFile ID '{content_id}' after retries")

    def _extract_all_files(self, data: Dict[str, Any], token: str) -> List[Dict[str, Any]]:
        """Recursively scan data object to collect all available files."""
        files: List[Dict[str, Any]] = []

        if data.get("type") == "file" and data.get("link"):
            files.append(data)
            return files

        children = data.get("children", {})
        if isinstance(children, dict):
            child_list = list(children.values())
        elif isinstance(children, list):
            child_list = children
        else:
            child_list = []

        for child in child_list:
            if not isinstance(child, dict):
                continue
            child_type = child.get("type", "file")
            if child_type == "file" and child.get("link"):
                files.append(child)
            elif child_type == "folder":
                sub_id = child.get("id") or child.get("code")
                if sub_id:
                    try:
                        sub_data = self.fetch_content_data(sub_id, token)
                        files.extend(self._extract_all_files(sub_data, token))
                    except Exception:
                        pass

        return files

    def resolve(self, url: str) -> ResolvedURL:
        """
        Resolve GoFile URL into a direct, high-speed authenticated download link.
        """
        content_id = self.extract_content_id(url)
        token = self._get_account_token()

        data = self.fetch_content_data(content_id, token)
        files = self._extract_all_files(data, token)

        if not files:
            raise RuntimeError(f"No downloadable files found in GoFile folder or content '{content_id}'")

        # Select target file: prefer archive/ROM formats or largest payload
        archive_exts = (".zip", ".rar", ".7z", ".tar.zst", ".tar.gz", ".tar.xz", ".tar", ".tgz", ".bin", ".img", ".iso")
        selected_file = None

        # 1. Search for archive extensions
        for f in files:
            name = (f.get("name") or "").lower()
            if any(name.endswith(ext) for ext in archive_exts):
                selected_file = f
                break

        # 2. Pick largest file if no archive extension found
        if not selected_file:
            selected_file = max(files, key=lambda f: f.get("size", 0))

        direct_url = selected_file.get("link")
        if not direct_url:
            raise RuntimeError(f"Target file '{selected_file.get('name')}' in GoFile folder '{content_id}' has no direct download link")

        filename = selected_file.get("name") or f"gofile_{content_id}.zip"
        file_size = selected_file.get("size")

        download_headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Authorization": f"Bearer {token}",
            "Origin": "https://gofile.io",
            "Referer": f"https://gofile.io/d/{content_id}"
        }
        cookies = {
            "accountToken": token
        }

        return ResolvedURL(
            original_url=url,
            direct_url=direct_url,
            filename=filename,
            file_size=file_size,
            headers=download_headers,
            cookies=cookies,
            supports_ranges=True
        )
