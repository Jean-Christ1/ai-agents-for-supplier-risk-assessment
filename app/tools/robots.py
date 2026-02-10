"""Robots.txt compliance checker.

Author: Armand Amoussou
"""

from __future__ import annotations

import urllib.robotparser
from functools import lru_cache
from urllib.parse import urlparse

from app.observability.logger import get_logger

logger = get_logger("robots")

USER_AGENT = "SupplierRiskBot/1.0"


@lru_cache(maxsize=128)
def _fetch_robot_parser(scheme_host: str) -> urllib.robotparser.RobotFileParser:
    """Fetch and parse robots.txt for a given scheme+host."""
    rp = urllib.robotparser.RobotFileParser()
    robots_url = f"{scheme_host}/robots.txt"
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        logger.warning("robots_fetch_failed", robots_url=robots_url)
    return rp


def is_allowed(url: str, user_agent: str = USER_AGENT) -> bool:
    """Check if the URL is allowed by robots.txt rules.

    Returns True if allowed or if robots.txt is unavailable (permissive default).
    """
    parsed = urlparse(url)
    scheme_host = f"{parsed.scheme}://{parsed.netloc}"
    try:
        rp = _fetch_robot_parser(scheme_host)
        allowed = rp.can_fetch(user_agent, url)
        if not allowed:
            logger.info("robots_disallowed", url=url, user_agent=user_agent)
        return allowed
    except Exception:
        logger.warning("robots_check_error", url=url)
        return True


def clear_cache() -> None:
    """Clear the robots.txt parser cache."""
    _fetch_robot_parser.cache_clear()
