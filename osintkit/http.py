"""Cliente HTTP con rate limiting, reintentos, caché y respeto de robots.txt."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .config import Settings

# Rutas que no deben pasar por la comprobacion de robots.txt.
_ROBOTS_EXEMPT_PATHS = ("/robots.txt",)


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
    """Envoltorio de httpx con pausas, reintentos y respeto de robots.txt."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        proxy = self.settings.proxy
        if proxy and proxy.lower().startswith("http://") and not self.settings.allow_insecure_proxy:
            raise ValueError(
                f"proxy inseguro '{proxy}': usa https:// (o ssl://, socks5://) "
                "o define OSINTKIT_ALLOW_INSECURE_PROXY=1 para forzarlo."
            )
        self._client = httpx.Client(
            follow_redirects=True,
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
        """Carga (y cachea) el robots.txt del host de `url`. None si no hay."""
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        parser: RobotFileParser | None = None
        try:
            resp = self._client.get(f"{origin}/robots.txt")
            if resp.status_code == 200 and "html" not in resp.headers.get("content-type", ""):
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
        except httpx.HTTPError:
            parser = None
        self._robots[origin] = parser
        return parser

    def robots_allowed(self, url: str) -> bool:
        """True si robots.txt permite acceder a `url` con nuestro user-agent."""
        if not self.settings.respect_robots:
            return True
        parsed = urlparse(url)
        if parsed.path in _ROBOTS_EXEMPT_PATHS:
            return True
        parser = self._robots_for(url)
        if parser is None:
            return True  # sin robots.txt => permitido
        try:
            return parser.can_fetch(self.settings.user_agent, url)
        except Exception:
            return True

    # -- peticiones ---------------------------------------------------------

    def get(self, url: str, *, use_cache: bool = True, user_agent: str | None = None, check_robots: bool = True) -> Response:
        if check_robots and not self.robots_allowed(url):
            return Response(
                url=url,
                status=0,
                text="",
                headers={"error": "bloqueado por robots.txt"},
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
                resp = self._client.get(url, headers=headers)
                body = resp.text[: self.settings.max_bytes]
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
