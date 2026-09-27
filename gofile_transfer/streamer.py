"""Zero-Disk Concurrent Streaming Pipe: Pipes incoming download stream directly to GoFile upload endpoint."""

import os
import time
import requests
from typing import Optional, Callable, Iterator

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

from .resolvers import ResolvedURL
from .uploader import GoFileUploader, GoFileResult


class StreamWrapper:
    """Wrapper that reads from an incoming HTTP response stream and acts as a file-like object for MultipartEncoder."""

    def __init__(self, response_stream: requests.Response, file_size: Optional[int] = None, chunk_size: int = 512 * 1024):
        self.response = response_stream
        self.file_size = file_size
        self.chunk_size = chunk_size
        self.stream_iter = self.response.iter_content(chunk_size=self.chunk_size)
        self.buffer = b""
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        if size == -1:
            return b"".join(self.stream_iter)

        while len(self.buffer) < size:
            try:
                chunk = next(self.stream_iter)
                if not chunk:
                    break
                self.buffer += chunk
            except StopIteration:
                break

        res = self.buffer[:size]
        self.buffer = self.buffer[size:]
        self.bytes_read += len(res)
        return res

    def __len__(self):
        if self.file_size is not None:
            return self.file_size
        raise TypeError("Unknown file size")


class DirectStreamPipe:
    """Executes zero-disk simultaneous download & upload transfer."""

    def __init__(self, uploader: Optional[GoFileUploader] = None, chunk_size: int = 512 * 1024):
        self.uploader = uploader or GoFileUploader()
        self.chunk_size = chunk_size

    def transfer_stream(
        self,
        resolved: ResolvedURL,
        folder_id: Optional[str] = None,
        custom_filename: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> GoFileResult:
        """Stream bytes directly from source URL into GoFile without touching local disk."""
        filename = custom_filename or resolved.filename or "streamed_file.bin"
        server = self.uploader.get_fastest_server()
        upload_url = f"https://{server}.gofile.io/contents/uploadfile"

        # Open incoming stream
        in_headers = resolved.headers.copy()
        in_headers["User-Agent"] = "Wget/1.21.3"

        session = requests.Session()
        in_res = session.get(
            resolved.direct_url,
            headers=in_headers,
            cookies=resolved.cookies,
            stream=True,
            timeout=30
        )
        in_res.raise_for_status()

        total_size = resolved.file_size
        if not total_size and "Content-Length" in in_res.headers:
            try:
                total_size = int(in_res.headers["Content-Length"])
            except ValueError:
                pass

        stream_obj = StreamWrapper(in_res, file_size=total_size, chunk_size=self.chunk_size)

        if HAS_TOOLBELT:
            fields = {"file": (filename, stream_obj, "application/octet-stream")}
            if folder_id:
                fields["folderId"] = folder_id
            if self.uploader.token:
                fields["token"] = self.uploader.token

            encoder = MultipartEncoder(fields=fields)

            if HAS_RICH:
                with Progress(
                    TextColumn("[bold magenta]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                ) as progress:
                    task = progress.add_task(f"⚡ Live Stream Pipe ({server}) {filename}", total=total_size or 0)

                    def _monitor_callback(monitor):
                        progress.update(task, completed=monitor.bytes_read)
                        if progress_callback:
                            progress_callback(monitor.bytes_read, total_size or 0)

                    monitor = MultipartEncoderMonitor(encoder, _monitor_callback)
                    headers = {"Content-Type": monitor.content_type}
                    if self.uploader.token:
                        headers["Authorization"] = f"Bearer {self.uploader.token}"

                    out_res = self.uploader.session.post(upload_url, data=monitor, headers=headers, timeout=900)
            else:
                def _monitor_callback(monitor):
                    if progress_callback:
                        progress_callback(monitor.bytes_read, total_size or 0)

                monitor = MultipartEncoderMonitor(encoder, _monitor_callback)
                headers = {"Content-Type": monitor.content_type}
                if self.uploader.token:
                    headers["Authorization"] = f"Bearer {self.uploader.token}"

                out_res = self.uploader.session.post(upload_url, data=monitor, headers=headers, timeout=900)
        else:
            files = {"file": (filename, stream_obj.read(), "application/octet-stream")}
            data_payload = {}
            if folder_id:
                data_payload["folderId"] = folder_id
            if self.uploader.token:
                data_payload["token"] = self.uploader.token
            headers = {}
            if self.uploader.token:
                headers["Authorization"] = f"Bearer {self.uploader.token}"
            out_res = self.uploader.session.post(upload_url, files=files, data=data_payload, headers=headers, timeout=900)

        out_res.raise_for_status()
        res_data = out_res.json()

        if res_data.get("status") != "ok":
            raise RuntimeError(f"GoFile stream upload failed: {res_data}")

        data = res_data["data"]
        return GoFileResult(
            download_page=data.get("downloadPage", f"https://gofile.io/d/{data.get('code', '')}"),
            code=data.get("code", ""),
            file_id=data.get("fileId", ""),
            file_name=data.get("fileName", filename),
            parent_folder=data.get("parentFolder"),
            md5=data.get("md5")
        )
