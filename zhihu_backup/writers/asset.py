from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import requests

from zhihu_backup.storage.base import StorageEngine

_IMG_RE = re.compile(r"!\[(?P<alt>.*?)\]\((?P<link>.+?)\)")


class AssetWriter:
    def __init__(
        self,
        assets_root: Path,
        engine: StorageEngine,
        session: Optional[requests.Session] = None,
        *,
        workers: int = 8,
    ):
        self.assets_root = Path(assets_root)
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self.engine = engine
        self.session = session  # retained for API compat; image GETs use requests.get
        self.workers = max(1, int(workers))

    def ensure_local(self, url: str) -> Optional[Path]:
        if not (url.startswith("http://") or url.startswith("https://")):
            return None
        cached = self._cached_path(url)
        if cached:
            return cached
        downloaded = self._download(url)
        if not downloaded:
            return None
        content, content_type = downloaded
        return self._store(url, content, content_type)

    def localize_markdown(self, md_body: str, md_dir: Path) -> str:
        urls = self._unique_http_urls(md_body)
        resolved: dict[str, Optional[Path]] = {}
        to_fetch: list[str] = []
        for url in urls:
            cached = self._cached_path(url)
            if cached:
                resolved[url] = cached
            else:
                to_fetch.append(url)

        if to_fetch:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = {pool.submit(self._download, url): url for url in to_fetch}
                for fut in as_completed(futures):
                    url = futures[fut]
                    try:
                        downloaded = fut.result()
                    except Exception:
                        downloaded = None
                    if downloaded:
                        content, content_type = downloaded
                        resolved[url] = self._store(url, content, content_type)
                    else:
                        resolved[url] = None

        out_lines = []
        for line in md_body.splitlines():
            parts = []
            last = 0
            for match in _IMG_RE.finditer(line):
                parts.append(line[last : match.start()])
                alt = match.group("alt")
                url = match.group("link")
                local = resolved.get(url)
                if local:
                    try:
                        rel = os.path.relpath(local, md_dir)
                    except ValueError:
                        rel = str(local)
                    parts.append(f"![{alt}]({rel.replace(os.sep, '/')})")
                else:
                    parts.append(f"![{alt}]({url})")
                last = match.end()
            parts.append(line[last:])
            out_lines.append("".join(parts))
        return "\n".join(out_lines)

    def _cached_path(self, url: str) -> Optional[Path]:
        cached = self.engine.get_asset_path(url)
        if cached and Path(cached).exists():
            return Path(cached)
        return None

    def _store(self, url: str, content: bytes, content_type: str) -> Path:
        ext = self._ext_from_meta(url, content_type)
        name = f"{hashlib.md5(url.encode('utf-8')).hexdigest()[:16]}{ext}"
        path = self.assets_root / name
        path.write_bytes(content)
        self.engine.set_asset_path(url, str(path))
        return path

    @staticmethod
    def _download(url: str) -> Optional[tuple[bytes, str]]:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
            return resp.content, content_type
        except Exception:
            return None

    @staticmethod
    def _unique_http_urls(md_body: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for match in _IMG_RE.finditer(md_body):
            url = match.group("link")
            if not (url.startswith("http://") or url.startswith("https://")):
                continue
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
        return out

    @staticmethod
    def _ext_from_meta(url: str, content_type: str) -> str:
        mime = (content_type or "").lower()
        mapping = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }
        if mime in mapping:
            return mapping[mime]
        path = urllib.parse.urlparse(url).path
        _, ext = os.path.splitext(path)
        if ext.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}:
            return ".jpg" if ext.lower() == ".jpeg" else ext.lower()
        return ".jpg"
