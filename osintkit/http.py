"""HTTP client with rate limiting, retries, caching, and robots.txt compliance."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .config import Settings

# Paths that must not go through robots.txt checks.
_ROBOTS_EXEMPT_PATHS = ("/robots.txt",)
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 20


@dataclass
class Response:
    url: str
    status: int
    text: str
    headers: dict[str, str]
    elapsed_ms: int

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400


class Fetcher:
    """httpx wrapper with throttling, retries, and robots.txt compliance."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        proxy = self.settings.proxy
        if (
            proxy
            and proxy.lower().startswith("http://")
            and not self.settings.allow_insecure_proxy
        ):
            raise ValueError(
                f"insecure proxy '{proxy}': use https:// (or ssl://, socks5://) "
                "or set OSINTKIT_ALLOW_INSECURE_PROXY=1 to force it."
            )
        self._client = httpx.Client(
            follow_redirects=False,
            headers={"User-Agent": self.settings.user_agent},
            timeout=self.settings.timeout,
            proxy=self.settings.proxy,
        )
        self._last_request = 0.0
        self._cache: dict[str, Response] = {}
        self._robots: dict[str, RobotFileParser | None] = {}

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        wait = self.settings.delay - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    # -- robots.txt ---------------------------------------------------------

    def _robots_for(self, url: str) -> RobotFileParser | None:
        """Loads (and caches) robots.txt for the host of `url`. None if misyesng."""
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        parser: RobotFileParser | None = None
        try:
            resp = self._client.get(f"{origin}/robots.txt")
            if resp.status_code == 200 and "html" not in resp.headers.get(
                "content-type", ""
            ):
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
        except httpx.HTTPError:
            parser = None
        self._robots[origin] = parser
        return parser

    def robots_allowed(self, url: str, *, user_agent: str | None = None) -> bool:
        """True if robots.txt allows accesyesng `url` with our user-agent."""
        if not self.settings.respect_robots:
            return True
        parsed = urlparse(url)
        if parsed.path in _ROBOTS_EXEMPT_PATHS:
            return True
        parser = self._robots_for(url)
        if parser is None:
            return True  # no robots.txt => allowed
        try:
            return parser.can_fetch(user_agent or self.settings.user_agent, url)
        except Exception:
            return True

    # -- peticiones ---------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        use_cache: bool = True,
        user_agent: str | None = None,
        check_robots: bool = True,
        allowed_hosts: set[str] | None = None,
    ) -> Response:
        if check_robots and not self.robots_allowed(url, user_agent=user_agent):
            return Response(
                url=url,
                status=0,
                text="",
                headers={"error": "blocked by robots.txt"},
                elapsed_ms=0,
            )

        cache_key = url
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        last_error: Exception | None = None
        for attempt in range(self.settings.retries + 1):
            self._throttle()
            start = time.monotonic()
            try:
                headers = {"User-Agent": user_agent} if user_agent else None
                request_url = url
                for redirect_count in range(_MAX_REDIRECTS + 1):
                    with self._client.stream(
                        "GET", request_url, headers=headers
                    ) as resp:
                        location = resp.headers.get("location")
                        if resp.status_code in _REDIRECT_STATUSES and location:
                            next_url = urljoin(str(resp.url), location)
                            next_parsed = urlparse(next_url)
                            if next_parsed.scheme not in ("http", "https"):
                                return Response(
                                    url=str(resp.url),
                                    status=0,
                                    text="",
                                    headers={
                                        "error": "redirect to unsupported URL scheme"
                                    },
                                    elapsed_ms=int((time.monotonic() - start) * 1000),
                                )
                            if (
                                allowed_hosts is not None
                                and next_parsed.netloc.lower()
                                not in {host.lower() for host in allowed_hosts}
                            ):
                                return Response(
                                    url=str(resp.url),
                                    status=0,
                                    text="",
                                    headers={"error": "redirect outside allowed hosts"},
                                    elapsed_ms=int((time.monotonic() - start) * 1000),
                                )
                            if check_robots and not self.robots_allowed(
                                next_url, user_agent=user_agent
                            ):
                                return Response(
                                    url=next_url,
                                    status=0,
                                    text="",
                                    headers={"error": "redirect blocked by robots.txt"},
                                    elapsed_ms=int((time.monotonic() - start) * 1000),
                                )
                            if redirect_count == _MAX_REDIRECTS:
                                return Response(
                                    url=str(resp.url),
                                    status=0,
                                    text="",
                                    headers={"error": "too many redirects"},
                                    elapsed_ms=int((time.monotonic() - start) * 1000),
                                )
                            request_url = next_url
                            continue

                        body_bytes = bytearray()
                        read_limit = max(0, self.settings.max_bytes)
                        if read_limit:
                            for chunk in resp.iter_bytes():
                                remaining = read_limit - len(body_bytes)
                                body_bytes.extend(chunk[:remaining])
                                if len(body_bytes) >= read_limit:
                                    break
                        encoding = resp.encoding or "utf-8"
                        try:
                            body = body_bytes.decode(encoding, errors="replace")
                        except LookupError:
                            body = body_bytes.decode("utf-8", errors="replace")
                        result = Response(
                            url=str(resp.url),
                            status=resp.status_code,
                            text=body,
                            headers=dict(resp.headers),
                            elapsed_ms=int((time.monotonic() - start) * 1000),
                        )
                        if use_cache:
                            self._cache[cache_key] = result
                        return result
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))

        return Response(
            url=url,
            status=0,
            text="",
            headers={"error": str(last_error)},
            elapsed_ms=0,
        )
