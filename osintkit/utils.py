"""Utility functions for osintkit."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urljoin


def normalize_url(url: str) -> str:
    """Normalize a URL by removing fragments and trailing slashes."""
    from urllib.parse import urldefrag
    url, _ = urldefrag(url)
    return url.rstrip("/") or url


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs are on the same domain."""
    return urlparse(url1).netloc == urlparse(url2).netloc


def clean_text(text: str | None) -> str:
    """Clean whitespace from text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc


def safe_get(d: dict, *keys, default=None):
    """Safely get nested dictionary values."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d
