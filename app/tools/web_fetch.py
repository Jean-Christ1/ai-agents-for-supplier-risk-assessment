"""Web content fetcher with allowlist, robots.txt, rate limiting, and caching.

Author: Armand Amoussou
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
import yaml

from app.observability.logger import get_logger
from app.tools.cache import LocalCache
from app.tools.rate_limit import DomainRateLimiter
from app.tools.robots import is_allowed

logger = get_logger("web_fetch")


def _load_allowlist(config_dir: str) -> dict:  # type: ignore[type-arg]
    """Load the domain allowlist from YAML config."""
    path = Path(config_dir) / "allowlist_domains.yml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


def _is_domain_allowed(url: str, allowlist: dict) -> bool:  # type: ignore[type-arg]
    """Check if the URL's domain is in the allowlist."""
    domain = urlparse(url).netloc
    allowed_domains = {e["domain"] for e in allowlist.get("domains", [])}
    return domain in allowed_domains


class WebFetcher:
    """Fetches web content with all safety guards."""

    def __init__(
        self,
        config_dir: str,
        cache_dir: str = "./cache/web",
        cache_ttl_hours: int = 24,
    ) -> None:
        self.allowlist = _load_allowlist(config_dir)
        self.user_agent = self.allowlist.get(
            "user_agent", "SupplierRiskBot/1.0"
        )
        settings = self.allowlist.get("settings", {})
        self.timeout = settings.get("request_timeout_seconds", 30)
        self.max_retries = settings.get("max_retries", 3)
        self.backoff_factor = settings.get("backoff_factor", 2.0)
        self.respect_robots = settings.get("respect_robots_txt", True)

        self.cache = LocalCache(cache_dir=cache_dir, ttl_hours=cache_ttl_hours)
        self.rate_limiter = DomainRateLimiter.from_allowlist(self.allowlist)

    def fetch(self, url: str) -> Optional[dict]:  # type: ignore[type-arg]
        """Fetch URL content with all guards.

        Returns dict with keys: url, content, content_hash, http_status, domain
        Returns None if blocked or failed.
        """
        # 1. Allowlist check
        if not _is_domain_allowed(url, self.allowlist):
            logger.warning("domain_not_allowed", url=url)
            return None

        # 2. Cache check
        cached = self.cache.get(url)
        if cached is not None:
            return {
                "url": url,
                "content": cached["content"],
                "content_hash": cached["content_hash"],
                "http_status": cached["http_status"],
                "domain": urlparse(url).netloc,
                "from_cache": True,
            }

        # 3. Robots.txt check
        if self.respect_robots and not is_allowed(url, self.user_agent):
            logger.warning("robots_blocked", url=url)
            return None

        # 4. Rate limiting
        if not self.rate_limiter.acquire(url, timeout=60.0):
            logger.warning("rate_limit_exceeded", url=url)
            return None

        # 5. HTTP fetch with retries
        headers = {"User-Agent": self.user_agent}
        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                content = resp.text
                c_hash = self.cache.put(url, content, resp.status_code)
                logger.info(
                    "web_fetch_ok",
                    url=url,
                    status=resp.status_code,
                    content_length=len(content),
                    attempt=attempt + 1,
                )
                return {
                    "url": url,
                    "content": content,
                    "content_hash": c_hash,
                    "http_status": resp.status_code,
                    "domain": urlparse(url).netloc,
                    "from_cache": False,
                }
            except requests.RequestException as e:
                last_error = str(e)
                wait = self.backoff_factor ** attempt
                logger.warning(
                    "web_fetch_retry",
                    url=url,
                    attempt=attempt + 1,
                    error=last_error,
                    wait_seconds=wait,
                )
                time.sleep(wait)

        logger.error("web_fetch_failed", url=url, error=last_error)
        return None
