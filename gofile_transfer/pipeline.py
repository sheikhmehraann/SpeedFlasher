"""Orchestrated 64-stream high-speed link-to-GoFile pipeline."""

import os
import sys
import time
import tempfile
from dataclasses import dataclass
from typing import Optional, List

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
    console = Console(force_terminal=True, legacy_windows=False)
except ImportError:
    HAS_RICH = False
    class DummyConsole:
        def print(self, *args, **kwargs):
            import re
            msg = " ".join(str(a) for a in args)
            clean_msg = re.sub(r'\[/?[a-zA-Z0-9 _=#]+\]', '', msg)
            print(clean_msg)

    console = DummyConsole()

from .resolvers import ResolverFactory, ResolvedURL
from .downloader import ParallelDownloader
from .uploader import GoFileUploader, GoFileResult

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


@dataclass
class TransferSummary:
    """Dataclass storing end-to-end performance and result details."""
    original_url: str
    filename: str
    file_size: int
    gofile_url: str
    gofile_code: str
    download_time: float
    upload_time: float
    total_time: float
    download_speed_mbps: float
    upload_speed_mbps: float


class TransferPipeline:
    """64-Stream parallel pipeline to resolve, download, upload, and format output."""

    def __init__(self, connections: int = 64, gofile_token: Optional[str] = None, keep_files: bool = False):
        self.factory = ResolverFactory()
        self.downloader = ParallelDownloader(num_connections=connections)
        self.uploader = GoFileUploader(token=gofile_token)
        self.keep_files = keep_files

    def process_url(self, url: str, output_dir: Optional[str] = None, folder_id: Optional[str] = None) -> TransferSummary:
        """Process a single URL: Resolve -> 64-Stream Parallel Download -> C-Level HTTP/2 Upload."""
        start_total = time.time()

        console.print(f"[bold cyan][>] Resolving URL:[/bold cyan] {url}")
        resolved: ResolvedURL = self.factory.resolve(url)

        console.print(f"[bold green][+] Link Resolved![/bold green] Direct URL: {resolved.direct_url[:80]}...")
        console.print(f"[bold white]File Name:[/bold white] {resolved.filename} | [bold white]Size:[/bold white] {f'{resolved.file_size / (1024*1024):.2f} MB' if resolved.file_size else 'Unknown'}")

        temp_dir = output_dir or tempfile.mkdtemp(prefix="gofile_transfer_")

        try:
            # 1. 64-Stream Parallel High-Speed Download
            start_dl = time.time()
            local_path = self.downloader.download(resolved, output_dir=temp_dir)
            dl_duration = max(time.time() - start_dl, 0.001)

            file_size = os.path.getsize(local_path)
            dl_speed = (file_size / (1024 * 1024)) / dl_duration
            console.print(f"[bold green][+] 64-Stream Download Completed![/bold green] Time: {dl_duration:.2f}s ({dl_speed:.2f} MB/s)")

            # 2. C-Level HTTP/2 Upload to Lowest-Latency Server
            start_ul = time.time()
            gofile_res = self.uploader.upload(local_path, folder_id=folder_id)
            ul_duration = max(time.time() - start_ul, 0.001)

            ul_speed = (file_size / (1024 * 1024)) / ul_duration
            total_duration = time.time() - start_total

            console.print(f"[bold green][+] C-Level Turbo Upload Completed![/bold green] Time: {ul_duration:.2f}s ({ul_speed:.2f} MB/s)")

            summary = TransferSummary(
                original_url=url,
                filename=resolved.filename or os.path.basename(local_path),
                file_size=file_size,
                gofile_url=gofile_res.download_page,
                gofile_code=gofile_res.code,
                download_time=dl_duration,
                upload_time=ul_duration,
                total_time=total_duration,
                download_speed_mbps=dl_speed,
                upload_speed_mbps=ul_speed
            )

            self.print_summary_panel(summary)
            return summary

        finally:
            if not self.keep_files and temp_dir and os.path.exists(temp_dir) and not output_dir:
                try:
                    for f in os.listdir(temp_dir):
                        os.remove(os.path.join(temp_dir, f))
                    os.rmdir(temp_dir)
                except Exception:
                    pass

    def print_summary_panel(self, summary: TransferSummary):
        """Render a clean terminal summary panel."""
        if HAS_RICH:
            table = Table(show_header=False, box=None)
            table.add_row("[bold cyan]GoFile Link:[/bold cyan]", f"[bold green u]{summary.gofile_url}[/bold green u]")
            table.add_row("[bold white]File Name:[/bold white]", summary.filename)
            table.add_row("[bold white]File Size:[/bold white]", f"{summary.file_size / (1024 * 1024):.2f} MB")
            table.add_row("[bold white]Download Speed (64x):[/bold white]", f"{summary.download_speed_mbps:.2f} MB/s ({summary.download_time:.2f}s)")
            table.add_row("[bold white]Upload Speed (C-Level):[/bold white]", f"{summary.upload_speed_mbps:.2f} MB/s ({summary.upload_time:.2f}s)")
            table.add_row("[bold white]Total Duration:[/bold white]", f"{summary.total_time:.2f}s")

            console.print(Panel(table, title="[+] ⚡ 64-Stream Turbo Transfer Completed", border_style="bold green"))
        else:
            print("\n" + "=" * 65)
            print("         ⚡ 64-Stream Turbo Transfer Completed")
            print(f"  GoFile Link           : {summary.gofile_url}")
            print(f"  File Name             : {summary.filename}")
            print(f"  File Size             : {summary.file_size / (1024 * 1024):.2f} MB")
            print(f"  Download Speed (64x)  : {summary.download_speed_mbps:.2f} MB/s ({summary.download_time:.2f}s)")
            print(f"  Upload Speed (C-Level): {summary.upload_speed_mbps:.2f} MB/s ({summary.upload_time:.2f}s)")
            print(f"  Total Duration        : {summary.total_time:.2f}s")
            print("=" * 65 + "\n")
