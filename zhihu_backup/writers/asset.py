from __future__ import annotations

import hashlib
import os
import urllib.parse
from pathlib import Path
from typing import Optional

import requests

from zhihu_backup.storage.base import StorageEngine


class AssetWriter:
    def __init__(self, assets_root: Path, engine: StorageEngine, session: Optional[requests.Session] = None):
        self.assets_root = Path(assets_root)
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self.engine = engine
        self.session = session or requests.Session()

    def ensure_local(self, url: str) -> Optional[Path]:
        if not (url.startswith("http://") or url.startswith("https://")):
            return None
        cached = self.engine.get_asset_path(url)
        if cached and Path(cached).exists():
            return Path(cached)
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            ext = self._ext_from_response(url, resp)
            name = f"{hashlib.md5(url.encode('utf-8')).hexdigest()[:16]}{ext}"
            path = self.assets_root / name
            path.write_bytes(resp.content)
            self.engine.set_asset_path(url, str(path))
            return path
        except Exception:
            return None

    def localize_markdown(self, md_body: str, md_dir: Path) -> str:
        import re

        pattern = r"!\[(?P<alt>.*?)\]\((?P<link>.+?)\)"
        out_lines = []
        for line in md_body.splitlines():
            parts = []
            last = 0
            for match in re.finditer(pattern, line):
                parts.append(line[last:match.start()])
                alt = match.group("alt")
                url = match.group("link")
                local = self.ensure_local(url)
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

    @staticmethod
    def _ext_from_response(url: str, resp: requests.Response) -> str:
        mime = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
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
