"""Web content parser: extracts structured text from HTML.

Author: Armand Amoussou
"""

from __future__ import annotations

from typing import Optional

from app.observability.logger import get_logger

logger = get_logger("web_parse")


def parse_html_to_text(html_content: str, url: str = "") -> Optional[str]:
    """Extract main textual content from HTML using trafilatura, with bs4 fallback."""
    if not html_content or not html_content.strip():
        return None

    # Primary: trafilatura
    try:
        import trafilatura

        text = trafilatura.extract(html_content, include_comments=False)
        if text and len(text.strip()) > 50:
            logger.debug("parse_trafilatura_ok", url=url, length=len(text))
            return text
    except Exception as e:
        logger.warning("parse_trafilatura_error", url=url, error=str(e))

    # Fallback: BeautifulSoup
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        if text and len(text.strip()) > 50:
            logger.debug("parse_bs4_ok", url=url, length=len(text))
            return text
    except Exception as e:
        logger.warning("parse_bs4_error", url=url, error=str(e))

    logger.warning("parse_no_content", url=url)
    return None


def extract_snippets(text: str, max_snippet_length: int = 240) -> list[str]:
    """Split text into meaningful snippets for evidence items."""
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    snippets = []
    for para in paragraphs:
        if len(para) <= max_snippet_length:
            snippets.append(para)
        else:
            snippets.append(para[:max_snippet_length])
    return snippets[:20]  # Cap at 20 snippets


def load_golden_content(file_path: str) -> Optional[str]:
    """Load content from a local golden test file."""
    try:
        with open(file_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("golden_file_not_found", path=file_path)
        return None
