"""Rastreo acotado y respetuoso: robots.txt, profundidad y deduplicación."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from ..config import USER_AGENT_TOOL
from ..http import Fetcher


@dataclass
class CrawlResult:
    url: str
    status: int
    depth: int
    title: str | None = None
    links_found: int = 0
    error: str | None = None


@dataclass
class CrawlConfig:
    start_url: str
    max_depth: int = 1
    max_pages: int = 25
    stay_on_host: bool = True
    respect_robots: bool = True
    user_agent: str = USER_AGENT_TOOL
    include: tuple[str, ...] = field(default_factory=tuple)
    exclude: tuple[str, ...] = field(default_factory=tuple)


def _normalize(url: str) -> str:
    url, _ = urldefrag(url)
    return url.rstrip("/") or url


def _allowed(include: tuple[str, ...], exclude: tuple[str, ...], url: str) -> bool:
    if include and not any(token in url for token in include):
        return False
    if any(token in url for token in exclude):
        return False
    return True


def load_robots(
    fetcher: Fetcher, start_url: str, user_agent: str
) -> RobotFileParser | None:
    parsed = urlparse(start_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    response = fetcher.get(
        robots_url,
        user_agent=user_agent,
        allowed_hosts={parsed.netloc},
    )
    if not response.ok or "html" in response.headers.get("content-type", ""):
        return None
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser


def crawl(fetcher: Fetcher, config: CrawlConfig) -> list[CrawlResult]:
    """Scoped BFS. Returns one row per visited page."""
    start = _normalize(config.start_url)
    start_host = urlparse(start).netloc
    robots = (
        load_robots(fetcher, start, config.user_agent)
        if config.respect_robots
        else None
    )

    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen: set[str] = {start}
    results: list[CrawlResult] = []

    while queue and len(results) < config.max_pages:
        url, depth = queue.popleft()

        if robots and not robots.can_fetch(config.user_agent, url):
            results.append(
                CrawlResult(
                    url=url, status=0, depth=depth, error="blocked by robots.txt"
                )
            )
            continue
        if not _allowed(config.include, config.exclude, url):
            continue

        # Crawl manages robots.txt itself (con su propio UA), ayes
        # que evitamos la doble comprobacion del Fetcher.
        response = fetcher.get(
            url,
            use_cache=False,
            check_robots=config.respect_robots,
            user_agent=config.user_agent,
            allowed_hosts={start_host} if config.stay_on_host else None,
        )
        soup = BeautifulSoup(response.text, "html.parser") if response.ok else None
        title = soup.title.get_text(strip=True) if soup and soup.title else None

        found_links: set[str] = set()
        if soup is not None:
            for anchor in soup.find_all("a", href=True):
                target = _normalize(urljoin(response.url or url, anchor["href"]))
                parsed = urlparse(target)
                if parsed.scheme not in ("http", "https"):
                    continue
                if config.stay_on_host and parsed.netloc != start_host:
                    continue
                if target not in seen:
                    seen.add(target)
                    found_links.add(target)
                    if depth + 1 <= config.max_depth:
                        queue.append((target, depth + 1))

        results.append(
            CrawlResult(
                url=response.url,
                status=response.status,
                depth=depth,
                title=title,
                links_found=len(found_links),
                error=(
                    None
                    if response.ok
                    else response.headers.get("error") or f"HTTP {response.status}"
                ),
            )
        )

    return results
