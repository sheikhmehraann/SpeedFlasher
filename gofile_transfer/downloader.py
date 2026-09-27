"""Ultra-fast parallel HTTP downloader with aria2c multi-connection acceleration and RAM disk buffering."""

import os
import sys
import time
import shutil
try:
    import httpx
except ImportError:
    httpx = None
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable, List

try:
    from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from .resolvers import ResolvedURL


class ParallelDownloader:
    """High-speed parallel downloader with native aria2c acceleration and RAM disk optimization."""

    def __init__(self, num_connections: int = 16, chunk_size: int = 2 * 1024 * 1024, max_retries: int = 3):
        self.num_connections = num_connections
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.has_aria2 = shutil.which("aria2c") is not None

    def get_optimal_directory(self, requested_dir: Optional[str] = None) -> str:
        """Use Linux RAM disk /dev/shm if available for zero disk latency."""
        if requested_dir and requested_dir != ".":
            return requested_dir
        if sys.platform.startswith("linux") and os.path.exists("/dev/shm") and os.access("/dev/shm", os.W_OK):
            return "/dev/shm"
        return requested_dir or "."

    def _is_valid_download(self, file_path: str, expected_size: Optional[int]) -> bool:
        """Validate that the downloaded file is a real binary payload and not a tiny HTML error page."""
        if not os.path.exists(file_path):
            return False
        sz = os.path.getsize(file_path)
        if sz < 1024:
            return False
        if expected_size and expected_size > 10 * 1024 * 1024 and sz < (expected_size * 0.85):
            return False
        # Reject HTML error pages saved as archives
        try:
            with open(file_path, "rb") as f:
                head = f.read(512)
                if b"<!DOCTYPE" in head or b"<html" in head or b"<HTML" in head or b"<head" in head:
                    return False
        except Exception:
            pass
        return True

    def download(
        self,
        resolved: ResolvedURL,
        output_dir: str = ".",
        custom_filename: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """Download resolved URL using optimal 16-connection aria2c engine with fallback."""
        filename = custom_filename or resolved.filename or "downloaded_file.bin"
        target_dir = self.get_optimal_directory(output_dir)
        output_path = os.path.abspath(os.path.join(target_dir, filename))
        os.makedirs(target_dir, exist_ok=True)

        # 1. Try aria2c with researched optimal parameters
        if self.has_aria2 and not ("drive.google.com" in resolved.original_url or "drive.usercontent" in resolved.direct_url):
            try:
                success = self._download_aria2(resolved.direct_url, target_dir, filename, resolved.headers, resolved.cookies)
                if success and self._is_valid_download(output_path, resolved.file_size):
                    return output_path
                elif os.path.exists(output_path):
                    os.remove(output_path)
            except Exception:
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass

        # 2. Try native curl/curl.exe acceleration
        if (shutil.which("curl.exe") or shutil.which("curl")) and not ("drive.google.com" in resolved.original_url or "drive.usercontent" in resolved.direct_url):
            try:
                success = self._download_curl(resolved.direct_url, output_path, resolved.headers, resolved.cookies)
                if success and self._is_valid_download(output_path, resolved.file_size):
                    return output_path
                elif os.path.exists(output_path):
                    os.remove(output_path)
            except Exception:
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass

        # 3. Direct streaming download engine (100% reliable for Google Drive session streams)
        file_size = resolved.file_size
        supports_ranges = resolved.supports_ranges and file_size and file_size > (1 * 1024 * 1024)

        if supports_ranges and self.num_connections > 1:
            try:
                self._download_parallel(resolved, output_path, file_size, progress_callback)
            except Exception:
                self._download_single(resolved, output_path, progress_callback)
        else:
            self._download_single(resolved, output_path, progress_callback)

        if not self._is_valid_download(output_path, resolved.file_size):
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            raise RuntimeError(f"Download produced an invalid or corrupted file: {output_path}")

        return output_path

    def _download_curl(self, direct_url: str, output_path: str, headers: dict, cookies: dict) -> bool:
        """Download via native curl/curl.exe."""
        curl_bin = "curl.exe" if shutil.which("curl.exe") else "curl"
        cmd = [curl_bin, "-L", "-sSL", "-k", "-o", output_path]
        for k, v in headers.items():
            cmd.extend(["-H", f"{k}: {v}"])
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            cmd.extend(["-H", f"Cookie: {cookie_str}"])
        cmd.append(direct_url)
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        return res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0

    def _download_aria2(self, direct_url: str, output_dir: str, filename: str, headers: Optional[dict] = None, cookies: Optional[dict] = None) -> bool:
        """Download via native aria2c with researched optimal production flags."""
        alloc_mode = "falloc" if sys.platform.startswith("linux") else "none"
        cmd = [
            "aria2c",
            f"--max-connection-per-server={self.num_connections}",
            f"--split={self.num_connections}",
            "--min-split-size=1M",
            "--piece-length=1M",
            f"--file-allocation={alloc_mode}",
            "--disk-cache=128M",
            "--enable-mmap=true",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "--allow-overwrite=true",
            "--auto-file-renaming=false",
            "--conditional-get=true",
            "--max-tries=5",
            "--retry-wait=2",
            "--summary-interval=1",
            "--console-log-level=warn",
            "--dir", output_dir,
            "--out", filename
        ]
        if headers:
            for k, v in headers.items():
                if k.lower() not in ("user-agent", "host", "content-length"):
                    cmd.append(f"--header={k}: {v}")
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            cmd.append(f"--header=Cookie: {cookie_str}")

        cmd.append(direct_url)
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.returncode == 0

    def _download_single(self, resolved: ResolvedURL, output_path: str, progress_callback: Optional[Callable[[int, int], None]] = None):
        """Single-stream download with requests."""
        import requests
        headers = resolved.headers.copy()
        with requests.get(resolved.direct_url, headers=headers, cookies=resolved.cookies, stream=True, timeout=60) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("Content-Length", 0)) or resolved.file_size or 0
            downloaded = 0
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

    def _download_parallel(self, resolved: ResolvedURL, output_path: str, file_size: int, progress_callback: Optional[Callable[[int, int], None]] = None):
        """Multi-threaded range request download with parallel workers and pre-allocated disk writes."""
        workers = min(self.num_connections, max(1, file_size // (1024 * 1024)))
        part_size = file_size // workers
        ranges = []
        for i in range(workers):
            start = i * part_size
            end = file_size - 1 if i == workers - 1 else (start + part_size - 1)
            ranges.append((start, end, i))

        with open(output_path, "wb") as f:
            f.truncate(file_size)

        downloaded_bytes = 0

        if HAS_RICH:
            with Progress(
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(complete_style="bold green", finished_style="bold green"),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task(f"⚡ Parallel Download {os.path.basename(output_path)}", total=file_size)

                def _download_chunk(start: int, end: int, part_id: int):
                    nonlocal downloaded_bytes
                    range_headers = resolved.headers.copy()
                    range_headers["Range"] = f"bytes={start}-{end}"

                    for attempt in range(self.max_retries):
                        try:
                            if httpx is not None:
                                with httpx.Client(follow_redirects=True, timeout=60.0, cookies=resolved.cookies) as client:
                                    with client.stream("GET", resolved.direct_url, headers=range_headers) as response:
                                        response.raise_for_status()
                                        if response.status_code != 206 and workers > 1:
                                            raise RuntimeError(f"Server returned HTTP {response.status_code} instead of 206 Partial Content")
                                        current_pos = start
                                        with open(output_path, "rb+") as f:
                                            f.seek(start)
                                            for chunk in response.iter_bytes(chunk_size=self.chunk_size):
                                                if chunk:
                                                    f.write(chunk)
                                                    chunk_len = len(chunk)
                                                    current_pos += chunk_len
                                                    downloaded_bytes += chunk_len
                                                    progress.update(task, completed=downloaded_bytes)
                                                    if progress_callback:
                                                        progress_callback(downloaded_bytes, file_size)
                            else:
                                with requests.get(resolved.direct_url, headers=range_headers, cookies=resolved.cookies, stream=True, timeout=60.0) as response:
                                    response.raise_for_status()
                                    if response.status_code != 206 and workers > 1:
                                        raise RuntimeError(f"Server returned HTTP {response.status_code} instead of 206 Partial Content")
                                    current_pos = start
                                    with open(output_path, "rb+") as f:
                                        f.seek(start)
                                        for chunk in response.iter_content(chunk_size=self.chunk_size):
                                            if chunk:
                                                f.write(chunk)
                                                chunk_len = len(chunk)
                                                current_pos += chunk_len
                                                downloaded_bytes += chunk_len
                                                progress.update(task, completed=downloaded_bytes)
                                                if progress_callback:
                                                    progress_callback(downloaded_bytes, file_size)
                            return
                        except Exception as e:
                            if attempt == self.max_retries - 1:
                                raise RuntimeError(f"Chunk {part_id} failed after {self.max_retries} retries: {e}")
                            time.sleep(0.3)

                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = [executor.submit(_download_chunk, start, end, part_id) for start, end, part_id in ranges]
                    for future in as_completed(futures):
                        future.result()
        else:
            def _download_chunk(start: int, end: int, part_id: int):
                nonlocal downloaded_bytes
                range_headers = resolved.headers.copy()
                range_headers["Range"] = f"bytes={start}-{end}"

                for attempt in range(self.max_retries):
                    try:
                        if httpx is not None:
                            with httpx.Client(follow_redirects=True, timeout=60.0, cookies=resolved.cookies) as client:
                                with client.stream("GET", resolved.direct_url, headers=range_headers) as response:
                                    response.raise_for_status()
                                    if response.status_code != 206 and workers > 1:
                                        raise RuntimeError(f"Server returned HTTP {response.status_code} instead of 206 Partial Content")
                                    current_pos = start
                                    with open(output_path, "rb+") as f:
                                        f.seek(start)
                                        for chunk in response.iter_bytes(chunk_size=self.chunk_size):
                                            if chunk:
                                                f.write(chunk)
                                                chunk_len = len(chunk)
                                                current_pos += chunk_len
                                                downloaded_bytes += chunk_len
                                                if progress_callback:
                                                    progress_callback(downloaded_bytes, file_size)
                        else:
                            with requests.get(resolved.direct_url, headers=range_headers, cookies=resolved.cookies, stream=True, timeout=60.0) as response:
                                response.raise_for_status()
                                if response.status_code != 206 and workers > 1:
                                    raise RuntimeError(f"Server returned HTTP {response.status_code} instead of 206 Partial Content")
                                current_pos = start
                                with open(output_path, "rb+") as f:
                                    f.seek(start)
                                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                                        if chunk:
                                            f.write(chunk)
                                            chunk_len = len(chunk)
                                            current_pos += chunk_len
                                            downloaded_bytes += chunk_len
                                            if progress_callback:
                                                progress_callback(downloaded_bytes, file_size)
                        return
                    except Exception as e:
                        if attempt == self.max_retries - 1:
                            raise RuntimeError(f"Chunk {part_id} failed after {self.max_retries} retries: {e}")
                        time.sleep(0.3)

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_download_chunk, start, end, part_id) for start, end, part_id in ranges]
                for future in as_completed(futures):
                    future.result()
