from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests

from storage.base import StorageEngine

_IMG_RE = re.compile(r"!\[(?P<alt>.*?)\]\((?P<link>.+?)\)")
# Zhihu CDN size suffixes before file extension: v2-xxx_720w.jpg
_ZHIMG_SIZE_RE = re.compile(
    r"_(?:720w|1080w|1440w|hd|qhd|b|l|m|r|t|is|\d+x\d+)(?=\.(?:jpg|jpeg|png|gif|webp)$)",
    re.IGNORECASE,
)
_ZHIMG_HOST_RE = re.compile(r"(^|\.)zhimg\.com$", re.IGNORECASE)


@dataclass
class AssetRef:
    file: str
    path: str  # vault-relative e.g. assets/ab12….jpg
    source: str
    origin: str
    local_path: Path


def normalize_asset_url(url: str) -> str:
    """Strip Zhihu CDN size suffixes to prefer original image URL."""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return url
    host = (parsed.hostname or "").lower()
    if not host or not _ZHIMG_HOST_RE.search(host):
        return url
    path = parsed.path or ""
    new_path = _ZHIMG_SIZE_RE.sub("", path)
    if new_path == path:
        return url
    return urllib.parse.urlunparse(parsed._replace(path=new_path))


class AssetWriter:
    def __init__(
        self,
        assets_root: Path,
        engine: StorageEngine,
        session: requests.Session | None = None,
        *,
        workers: int = 8,
        asset_link: str = "wikilink",
    ):
        self.assets_root = Path(assets_root)
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self.engine = engine
        self.session = session
        self.workers = max(1, int(workers))
        mode = (asset_link or "wikilink").lower()
        if mode not in ("wikilink", "rel", "assets-root"):
            mode = "wikilink"
        self.asset_link = mode

    def ensure_local(self, url: str) -> Path | None:
        if not (url.startswith(("http://", "https://"))):
            return None
        ref = self._resolve_one(url)
        return ref.local_path if ref else None

    def localize_markdown(self, md_body: str, md_dir: Path) -> tuple[str, list[str], list[AssetRef]]:
        urls = self._unique_http_urls(md_body)
        resolved: dict[str, AssetRef | None] = {}
        to_fetch: list[str] = []
        for url in urls:
            cached = self._cached_ref(url)
            if cached:
                resolved[url] = cached
            else:
                to_fetch.append(url)

        if to_fetch:
            # Download in worker threads only; SQLite engine is not thread-safe.
            downloads: dict[str, tuple[bytes, str, str, str] | None] = {}
            # value: content, content_type, canonical_url, origin_url
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = {
                    pool.submit(self._download_prefer_origin, url): url for url in to_fetch
                }
                for fut in as_completed(futures):
                    url = futures[fut]
                    try:
                        downloads[url] = fut.result()
                    except Exception:
                        downloads[url] = None
            for source_url, packed in downloads.items():
                if not packed:
                    resolved[source_url] = None
                    continue
                content, content_type, canonical, origin = packed
                path = self._store(
                    canonical,
                    content,
                    content_type,
                    source_url=source_url,
                    origin_url=origin,
                )
                if source_url != canonical:
                    self.engine.set_asset_path(
                        source_url, str(path), source_url=source_url, origin_url=origin
                    )
                resolved[source_url] = AssetRef(
                    file=path.name,
                    path=f"assets/{path.name}",
                    source=source_url,
                    origin=origin,
                    local_path=path,
                )

        refs = [r for r in resolved.values() if r is not None]
        # stable unique by canonical origin
        by_origin: dict[str, AssetRef] = {}
        for r in refs:
            by_origin.setdefault(r.origin, r)
        refs = list(by_origin.values())
        asset_urls = [r.origin for r in refs]

        out_lines = []
        for line in md_body.splitlines():
            parts = []
            last = 0
            for match in _IMG_RE.finditer(line):
                parts.append(line[last : match.start()])
                alt = match.group("alt")
                url = match.group("link")
                ref = resolved.get(url)
                if ref:
                    parts.append(self._emit_image(alt, ref, md_dir))
                else:
                    parts.append(f"![{alt}]({url})")
                last = match.end()
            parts.append(line[last:])
            out_lines.append("".join(parts))
        return "\n".join(out_lines), asset_urls, refs

    def _emit_image(self, alt: str, ref: AssetRef, md_dir: Path) -> str:
        comments = (
            f"<!-- asset-source: {ref.source} -->\n"
            f"<!-- asset-origin: {ref.origin} -->\n"
        )
        if self.asset_link == "wikilink":
            body = f"![[{ref.path}]]"
        elif self.asset_link == "assets-root":
            body = f"![{alt}](/{ref.path})"
        else:
            try:
                rel = os.path.relpath(ref.local_path, md_dir)
            except ValueError:
                rel = str(ref.local_path)
            body = f"![{alt}]({rel.replace(os.sep, '/')})"
        return comments + body

    def _cached_ref(self, source_url: str) -> AssetRef | None:
        origin = normalize_asset_url(source_url)
        for key in (origin, source_url):
            cached = self.engine.get_asset_path(key)
            if cached and Path(cached).exists():
                path = Path(cached)
                meta = self.engine.get_asset_meta(key) if hasattr(self.engine, "get_asset_meta") else {}
                meta = meta or {}
                return AssetRef(
                    file=path.name,
                    path=f"assets/{path.name}",
                    source=str(meta.get("source_url") or source_url),
                    origin=str(meta.get("origin_url") or origin),
                    local_path=path,
                )
        return None

    def _download_prefer_origin(
        self, source_url: str
    ) -> tuple[bytes, str, str, str] | None:
        """Return (content, content_type, canonical_url, origin_url) or None."""
        origin = normalize_asset_url(source_url)
        if origin != source_url:
            downloaded = self._download(origin)
            if downloaded:
                content, content_type = downloaded
                return content, content_type, origin, origin
        downloaded = self._download(source_url)
        if not downloaded:
            return None
        content, content_type = downloaded
        canonical = origin if origin != source_url else source_url
        return content, content_type, canonical, origin

    def _resolve_one(self, source_url: str) -> AssetRef | None:
        if not source_url.startswith(("http://", "https://")):
            return None
        cached = self._cached_ref(source_url)
        if cached:
            return cached
        packed = self._download_prefer_origin(source_url)
        if not packed:
            return None
        content, content_type, canonical, origin = packed
        path = self._store(
            canonical, content, content_type, source_url=source_url, origin_url=origin
        )
        if source_url != canonical:
            self.engine.set_asset_path(
                source_url, str(path), source_url=source_url, origin_url=origin
            )
        return AssetRef(
            file=path.name,
            path=f"assets/{path.name}",
            source=source_url,
            origin=origin,
            local_path=path,
        )

    def _store(
        self,
        url: str,
        content: bytes,
        content_type: str,
        *,
        source_url: str,
        origin_url: str,
    ) -> Path:
        ext = self._ext_from_meta(url, content_type)
        name = f"{hashlib.md5(url.encode('utf-8')).hexdigest()[:16]}{ext}"
        path = self.assets_root / name
        path.write_bytes(content)
        self.engine.set_asset_path(
            url, str(path), source_url=source_url, origin_url=origin_url
        )
        return path

    @staticmethod
    def _download(url: str) -> tuple[bytes, str] | None:
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
            if not (url.startswith(("http://", "https://"))):
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
