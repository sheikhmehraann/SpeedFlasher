import os
from pathlib import Path
from gofile_transfer.resolvers.factory import ResolverFactory
from gofile_transfer.downloader import ParallelDownloader


class FastDownloader:
    @classmethod
    def download(cls, url: str, output_path: str, max_connections: int = 16) -> str:
        output_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.basename(output_path)

        print(f"[*] Resolving link: {url}")
        factory = ResolverFactory()
        resolved = factory.resolve(url)
        print(f"[+] Direct URL: {resolved.direct_url}")
        if resolved.filename:
            print(f"[+] Remote name: {resolved.filename}")

        if resolved.filename and "." in resolved.filename and "." not in filename:
            remote_ext = "".join(Path(resolved.filename).suffixes)
            filename = f"{filename}{remote_ext}"
        elif resolved.filename and not filename:
            filename = resolved.filename

        downloader = ParallelDownloader(num_connections=max_connections)
        downloaded_file = downloader.download(
            resolved=resolved,
            output_dir=output_dir,
            custom_filename=filename
        )

        if not os.path.exists(downloaded_file) or os.path.getsize(downloaded_file) < 1024:
            raise RuntimeError(f"Download failed or output file is empty: {downloaded_file}")

        try:
            with open(downloaded_file, "rb") as f:
                head = f.read(512)
                if b"<!DOCTYPE" in head or b"<html" in head or b"<HTML" in head or b"<head" in head:
                    raise RuntimeError("Download failed: Server returned an HTML error page.")
        except OSError:
            pass

        size_mb = os.path.getsize(downloaded_file) / (1024 * 1024)
        print(f"[+] Download complete: {downloaded_file} ({size_mb:.2f} MB)")
        return downloaded_file
