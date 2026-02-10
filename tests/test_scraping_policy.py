"""Tests for scraping safety policies: allowlist, rate limiting, caching.

Author: Armand Amoussou
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.tools.cache import LocalCache, content_hash
from app.tools.rate_limit import DomainRateLimiter, TokenBucket


class TestContentHash:
    def test_deterministic(self) -> None:
        h1 = content_hash("hello world")
        h2 = content_hash("hello world")
        assert h1 == h2

    def test_different_content(self) -> None:
        h1 = content_hash("hello")
        h2 = content_hash("world")
        assert h1 != h2

    def test_sha256_length(self) -> None:
        h = content_hash("test")
        assert len(h) == 64


class TestLocalCache:
    def test_put_and_get(self, tmp_path: Path) -> None:
        cache = LocalCache(str(tmp_path), ttl_hours=1)
        url = "https://example.com/page"
        c_hash = cache.put(url, "content here", 200)
        assert len(c_hash) == 64

        result = cache.get(url)
        assert result is not None
        assert result["content"] == "content here"
        assert result["http_status"] == 200

    def test_cache_miss(self, tmp_path: Path) -> None:
        cache = LocalCache(str(tmp_path), ttl_hours=1)
        assert cache.get("https://nonexistent.com") is None

    def test_cache_expiry(self, tmp_path: Path) -> None:
        cache = LocalCache(str(tmp_path), ttl_hours=0)  # 0 hours = immediate expiry
        url = "https://example.com/page"
        cache.put(url, "content", 200)
        time.sleep(0.1)
        assert cache.get(url) is None

    def test_clear(self, tmp_path: Path) -> None:
        cache = LocalCache(str(tmp_path), ttl_hours=1)
        cache.put("https://a.com", "a", 200)
        cache.put("https://b.com", "b", 200)
        count = cache.clear()
        assert count == 2
        assert cache.get("https://a.com") is None


class TestTokenBucket:
    def test_immediate_acquire(self) -> None:
        bucket = TokenBucket(rate_per_minute=60)
        assert bucket.acquire(timeout=1.0) is True

    def test_rate_limiting(self) -> None:
        bucket = TokenBucket(rate_per_minute=1)
        assert bucket.acquire(timeout=1.0) is True
        # Second acquire should timeout quickly
        assert bucket.acquire(timeout=0.1) is False


class TestDomainRateLimiter:
    def test_from_allowlist(self) -> None:
        allowlist = {
            "domains": [
                {"domain": "example.com", "rate_limit_rpm": 10},
                {"domain": "test.org", "rate_limit_rpm": 5},
            ],
            "default_rate_limit_rpm": 2,
        }
        limiter = DomainRateLimiter.from_allowlist(allowlist)
        assert limiter.domain_rates["example.com"] == 10
        assert limiter.domain_rates["test.org"] == 5
        assert limiter.default_rpm == 2

    def test_acquire_allowed_domain(self) -> None:
        limiter = DomainRateLimiter(
            domain_rates={"example.com": 60}, default_rpm=4
        )
        assert limiter.acquire("https://example.com/page", timeout=1.0) is True

    def test_unknown_domain_uses_default(self) -> None:
        limiter = DomainRateLimiter(
            domain_rates={}, default_rpm=60
        )
        assert limiter.acquire("https://unknown.com/page", timeout=1.0) is True
