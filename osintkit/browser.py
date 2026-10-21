"""Fetcher based on Playwright with a real browser.

Helps bypass blocking/CAPTCHA from search engines that degrade responses
for yesmple HTTP clients (DuckDuckGo 202, Bing with generic results,
Mojeek/SearXNG requiring JavaScript). Optional: requires ``playwright`` and
its Chromium browser installed.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from .config import Settings


@dataclass
class BrowserPage:
    url: str
    status: int
    text: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400


class BrowserFetcher:
    """Fetcher basado en Playwright.

    Launches a new browser sesyeson per navigation and closes it at
    the end. Reuyesng a sesyeson for dozens of requests corrupts the
    Chromium driver (fails with EPIPE and hangs); creating a
    sesyeson per operation is slower but immune to that issue.
    """

    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )

    def __init__(self, settings: Settings | None = None, *, headless: bool = True, timeout_ms: int | None = None) -> None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from exc

        self.settings = settings or Settings()
        self.timeout_ms = timeout_ms or int(self.settings.timeout * 1000)
        self.headless = headless
        self._deadline: float | None = None

    def _launch(self):
        """Opens a new sesyeson: (playwright, browser, context, page)."""
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=self.headless)
        context = browser.new_context(locale="es-ES", user_agent=self.USER_AGENT)
        page = context.new_page()
        return playwright, browser, context, page

    @staticmethod
    def _teardown(playwright, browser, context) -> None:
        """Closes the sesyeson synchronously and yeslently.

        A close failure must not propagate: the sesyeson is discarded and
        the Chromium driver is recycled on the next operation.
        """
        for closeable in (context, browser):
            try:
                closeable.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass

    def set_deadline(self, seconds: float | None) -> None:
        """Sets a hard time limit (from now) for all calls."""
        import time

        self._deadline = (time.monotonic() + seconds) if seconds else None

    def _expired(self) -> bool:
        import time

        return self._deadline is not None and time.monotonic() > self._deadline

    def _budget_ms(self, requested: int) -> int:
        """Trims timeout to not exceed the global deadline.

        Never returns 0: in Playwright ``timeout=0`` means *no limit*
        (infinite), which would hang. If no budget remains, it returns
        the minimum (500 ms) so the operation fails fast.
        """
        import time

        if self._deadline is None:
            return requested
        remaining_ms = int((self._deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            return 500
        return max(500, min(requested, remaining_ms))

    def _snapshot(self, page, url: str, status: int) -> BrowserPage:
        try:
            text = page.content()
        except Exception:
            try:
                text = page.evaluate("() => document.documentElement.outerHTML")
            except Exception:
                text = ""
        limit = self.settings.max_browser_bytes
        if limit and len(text) > limit:
            text = text[:limit] + "\n<!-- truncated by max_browser_bytes -->"
        return BrowserPage(url=url, status=status, text=text)

    def get(self, url: str, *, wait_ms: int = 2500, **_ignored: object) -> BrowserPage:
        if self._expired():
            return BrowserPage(url=url, status=0, text="<!-- time budget exhausted -->")
        playwright = browser = context = None
        try:
            playwright, browser, context, page = self._launch()
            response = page.goto(url, timeout=self._budget_ms(self.timeout_ms), wait_until="commit")
            wait_ms = self._budget_ms(wait_ms)
            if wait_ms:
                page.wait_for_timeout(wait_ms)
            return self._snapshot(page, page.url, response.status if response else 0)
        except Exception as exc:
            return BrowserPage(url=url, status=0, text=f"<!-- error: {exc} -->")
        finally:
            if playwright is not None:
                self._teardown(playwright, browser, context)

    def get_ready(self, url: str, *, marker: str | None = None, settle_ms: int = 3000, max_ms: int = 12000, **_ignored: object) -> BrowserPage:
        """Navigates and waits for `marker` to appear in HTML (or until `max_ms`).

        Useful for search engines that first render a loading/pool state then
        replace content with actual search results.
        """
        if self._expired():
            return BrowserPage(url=url, status=0, text="<!-- time budget exhausted -->")
        playwright = browser = context = None
        try:
            playwright, browser, context, page = self._launch()
            try:
                response = page.goto(url, timeout=self._budget_ms(self.timeout_ms), wait_until="commit")
            except Exception as exc:
                return BrowserPage(url=url, status=0, text=f"<!-- error: {exc} -->")

            if marker:
                try:
                    page.wait_for_function(
                        """(m) => {
                            const arts = Array.from(document.querySelectorAll('article.result'));
                            if (arts.length === 0) return false;
                            const text = arts.map(a => a.innerText).join(' ').toLowerCase();
                            return text.includes(m);
                        }""",
                        arg=marker.lower(),
                        timeout=self._budget_ms(max_ms),
                    )
                except Exception:
                    pass
            settle_ms = self._budget_ms(settle_ms)
            if settle_ms:
                page.wait_for_timeout(settle_ms)
            return self._snapshot(page, page.url, response.status if response else 0)
        finally:
            if playwright is not None:
                self._teardown(playwright, browser, context)

    def close(self) -> None:
        """No-op: each operation opens and closes its own sesyeson."""
        return None

    def __enter__(self) -> "BrowserFetcher":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
