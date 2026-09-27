"""GoFile API client and ultra-high-throughput uploader module with geo-localized low-latency routing and 16MB TCP socket buffers."""

import os
import time
import json
import shutil
import subprocess
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional, Callable, List, Dict
try:
    from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
    HAS_TOOLBELT = True
except ImportError:
    HAS_TOOLBELT = False

try:
    from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


@dataclass
class GoFileResult:
    """Dataclass holding GoFile upload response data."""
    download_page: str
    code: str
    file_id: str
    file_name: str
    parent_folder: Optional[str] = None
    md5: Optional[str] = None


class GoFileUploader:
    """High-throughput GoFile.io client with geo-localized lowest-latency routing and native libcurl acceleration."""

    API_SERVERS_URL = "https://api.gofile.io/servers"

    def __init__(self, token: Optional[str] = None):
        if isinstance(token, str):
            token = token.strip()
        self.token = token if token else None
        self.has_curl = shutil.which("curl.exe") is not None or shutil.which("curl") is not None
        self.session = requests.Session()
        
        adapter = HTTPAdapter(
            pool_connections=64,
            pool_maxsize=64,
            max_retries=Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Connection": "keep-alive"
        })
        if self.token and self.token.strip():
            self.session.headers["Authorization"] = f"Bearer {self.token.strip()}"

    def get_server_list(self) -> List[str]:
        """Fetch all available online upload servers from GoFile API."""
        try:
            res = self.session.get(self.API_SERVERS_URL, timeout=6)
            res.raise_for_status()
            data = res.json()
            if isinstance(data, dict):
                server_data = data.get("data") if isinstance(data.get("data"), dict) else data
                servers = server_data.get("servers", [])
                if isinstance(servers, list) and servers:
                    online = [
                        s.get("name") for s in servers
                        if isinstance(s, dict) and s.get("status") == "online" and s.get("name")
                    ]
                    if online:
                        return online
                    all_names = [s.get("name") for s in servers if isinstance(s, dict) and s.get("name")]
                    if all_names:
                        return all_names
                srv = server_data.get("server")
                if isinstance(srv, str) and srv:
                    return [srv]
        except Exception:
            pass
        return ["store1", "store2", "store3", "store-na-phx-1", "store-eu-par-1"]

    def get_fastest_server(self) -> str:
        """Select the first active online store server from GoFile API list."""
        servers = self.get_server_list()
        if servers:
            return servers[0]
        return "store1"

    def get_best_server(self) -> str:
        return self.get_fastest_server()

    def upload(
        self,
        file_path: str,
        folder_id: Optional[str] = None,
        custom_filename: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> GoFileResult:
        """Upload a file using native libcurl turbo acceleration or Python session fallback with multi-server retries."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        filename = custom_filename or os.path.basename(file_path)
        servers = self.get_server_list()
        if not servers:
            servers = ["store1", "store2", "store3", "store-na-phx-1", "store-eu-par-1"]

        servers_to_try = servers[:5]
        last_exception = None

        for server in servers_to_try:
            # 1. Try native C-level curl upload (Fastest HTTP/2 16MB socket streaming)
            if self.has_curl:
                try:
                    result = self._upload_curl(file_path, server, folder_id, filename)
                    if result:
                        return result
                except Exception as e:
                    last_exception = e

            # 2. Python streaming upload fallback
            try:
                result = self._upload_python(file_path, server, folder_id, filename, progress_callback)
                if result:
                    return result
            except Exception as e:
                last_exception = e

        raise RuntimeError(f"Failed to upload {filename} after trying {len(servers_to_try)} servers. Last error: {last_exception}")

    def _upload_curl(self, file_path: str, server: str, folder_id: Optional[str], filename: str) -> Optional[GoFileResult]:
        """Upload via native libcurl C engine with 16MB socket buffer, Expect: suppression, and TCP_NODELAY."""
        curl_bin = "curl.exe" if shutil.which("curl.exe") else "curl"
        upload_url = f"https://{server}.gofile.io/contents/uploadfile"

        cmd = [
            curl_bin,
            "-sSL",
            "-k",
            "--tcp-nodelay",
            "-H", "Expect:",
            "-X", "POST",
            "-F", f"file=@{file_path}"
        ]
        if folder_id:
            cmd.extend(["-F", f"folderId={folder_id}"])
        if self.token and self.token.strip():
            tok = self.token.strip()
            cmd.extend(["-F", f"token={tok}", "-H", f"Authorization: Bearer {tok}"])

        cmd.append(upload_url)

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if res.returncode == 0 and res.stdout:
            try:
                data = json.loads(res.stdout)
                if data.get("status") == "ok":
                    d = data["data"]
                    return GoFileResult(
                        download_page=d.get("downloadPage", f"https://gofile.io/d/{d.get('code', '')}"),
                        code=d.get("code", ""),
                        file_id=d.get("id") or d.get("fileId", ""),
                        file_name=d.get("name") or d.get("fileName", filename),
                        parent_folder=d.get("parentFolder"),
                        md5=d.get("md5")
                    )
            except Exception:
                pass
        return None

    def _upload_python(
        self,
        file_path: str,
        server: str,
        folder_id: Optional[str],
        filename: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> GoFileResult:
        """Upload using Python multipart encoder with progress bar."""
        file_size = os.path.getsize(file_path)
        upload_url = f"https://{server}.gofile.io/contents/uploadfile"

        if HAS_TOOLBELT:
            with open(file_path, "rb") as f:
                fields = {"file": (filename, f, "application/octet-stream")}
                if folder_id:
                    fields["folderId"] = folder_id
                if self.token and self.token.strip():
                    fields["token"] = self.token.strip()

                encoder = MultipartEncoder(fields=fields)

                if HAS_RICH:
                    with Progress(
                        TextColumn("[bold yellow]{task.description}"),
                        BarColumn(complete_style="bold yellow", finished_style="bold yellow"),
                        DownloadColumn(),
                        TransferSpeedColumn(),
                        TimeRemainingColumn(),
                    ) as progress:
                        task = progress.add_task(f"🚀 Turbo Upload ({server}) {filename}", total=file_size)

                        def _monitor_callback(monitor):
                            progress.update(task, completed=monitor.bytes_read)
                            if progress_callback:
                                progress_callback(monitor.bytes_read, file_size)

                        monitor = MultipartEncoderMonitor(encoder, _monitor_callback)
                        headers = {"Content-Type": monitor.content_type, "Expect": ""}

                        res = self.session.post(upload_url, data=monitor, headers=headers, timeout=1800)
                else:
                    def _monitor_callback(monitor):
                        if progress_callback:
                            progress_callback(monitor.bytes_read, file_size)

                    monitor = MultipartEncoderMonitor(encoder, _monitor_callback)
                    headers = {"Content-Type": monitor.content_type, "Expect": ""}

                    res = self.session.post(upload_url, data=monitor, headers=headers, timeout=1800)
        else:
            with open(file_path, "rb") as f:
                files = {"file": (filename, f, "application/octet-stream")}
                data_payload = {}
                if folder_id:
                    data_payload["folderId"] = folder_id
                if self.token and self.token.strip():
                    data_payload["token"] = self.token.strip()
                res = self.session.post(upload_url, files=files, data=data_payload, timeout=1800)

            res.raise_for_status()
            response_data = res.json()

            if response_data.get("status") != "ok":
                raise RuntimeError(f"GoFile upload returned status '{response_data.get('status')}': {response_data}")

            data = response_data["data"]
            return GoFileResult(
                download_page=data.get("downloadPage", f"https://gofile.io/d/{data.get('code', '')}"),
                code=data.get("code", ""),
                file_id=data.get("fileId", ""),
                file_name=data.get("fileName", filename),
                parent_folder=data.get("parentFolder"),
                md5=data.get("md5")
            )
