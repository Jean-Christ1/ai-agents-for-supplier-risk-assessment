"""Local file cache for web content with content hashing.

Author: Armand Amoussou
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from app.observability.logger import get_logger

logger = get_logger("cache")


def content_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class LocalCache:
    """File-based cache for web content with TTL."""

    def __init__(self, cache_dir: str = "./cache/web", ttl_hours: int = 24) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600

    def _key_path(self, url: str) -> Path:
        """Generate a cache file path from URL hash."""
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{url_hash}.json"

    def get(self, url: str) -> dict | None:  # type: ignore[type-arg]
        """Retrieve cached content if not expired. Returns None on miss."""
        path = self._key_path(url)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cached_at = data.get("cached_at", 0)
            if time.time() - cached_at > self.ttl_seconds:
                logger.debug("cache_expired", url=url)
                path.unlink(missing_ok=True)
                return None
            logger.debug("cache_hit", url=url)
            return data  # type: ignore[no-any-return]
        except (json.JSONDecodeError, KeyError):
            path.unlink(missing_ok=True)
            return None

    def put(
        self, url: str, content: str, http_status: int, metadata: dict | None = None  # type: ignore[type-arg]
    ) -> str:
        """Store content in cache. Returns content_hash."""
        c_hash = content_hash(content)
        data = {
            "url": url,
            "content": content,
            "content_hash": c_hash,
            "http_status": http_status,
            "cached_at": time.time(),
            "metadata": metadata or {},
        }
        path = self._key_path(url)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        logger.debug("cache_put", url=url, content_hash=c_hash)
        return c_hash

    def clear(self) -> int:
        """Remove all cached files. Returns count of removed files."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count
