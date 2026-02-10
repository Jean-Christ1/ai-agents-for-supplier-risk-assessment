"""Token-bucket rate limiter per domain.

Author: Armand Amoussou
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

from app.observability.logger import get_logger

logger = get_logger("rate_limit")


class TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, rate_per_minute: int) -> None:
        self.rate = rate_per_minute / 60.0  # tokens per second
        self.max_tokens = float(rate_per_minute)
        self.tokens = float(rate_per_minute)
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self, timeout: float = 60.0) -> bool:
        """Block until a token is available or timeout is reached."""
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
                self.last_refill = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.1)


class DomainRateLimiter:
    """Manages per-domain rate limiters."""

    def __init__(self, domain_rates: dict[str, int] | None = None, default_rpm: int = 4) -> None:
        self.domain_rates = domain_rates or {}
        self.default_rpm = default_rpm
        self.buckets: dict[str, TokenBucket] = {}
        self.lock = threading.Lock()

    def _get_bucket(self, domain: str) -> TokenBucket:
        with self.lock:
            if domain not in self.buckets:
                rpm = self.domain_rates.get(domain, self.default_rpm)
                self.buckets[domain] = TokenBucket(rpm)
            return self.buckets[domain]

    def acquire(self, url: str, timeout: float = 60.0) -> bool:
        """Wait for rate limit clearance for the given URL's domain."""
        domain = urlparse(url).netloc
        bucket = self._get_bucket(domain)
        ok = bucket.acquire(timeout=timeout)
        if not ok:
            logger.warning("rate_limit_timeout", domain=domain, url=url)
        return ok

    @classmethod
    def from_allowlist(cls, allowlist: dict) -> DomainRateLimiter:  # type: ignore[type-arg]
        """Build rate limiter from allowlist config dict."""
        domain_rates = {}
        for entry in allowlist.get("domains", []):
            domain_rates[entry["domain"]] = entry.get("rate_limit_rpm", 4)
        default_rpm = allowlist.get("default_rate_limit_rpm", 4)
        return cls(domain_rates=domain_rates, default_rpm=default_rpm)
