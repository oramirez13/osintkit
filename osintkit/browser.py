"""Fetcher basado en Playwright con un navegador real.

Permite superar el bloqueo/CAPTCHA de buscadores que degradan las respuestas
para clientes HTTP simples (DuckDuckGo 202, Bing con resultados genericos,
Mojeek/SearXNG exigiendo JavaScript). Es opcional: requiere ``playwright`` y
su navegador Chromium instalados.
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

    Lanza una sesion de navegador nueva por cada navegacion y la cierra al
    terminar. Reutilizar una sesion para decenas de peticiones corrompe el
    driver de Chromium (falla con EPIPE y termina colgandose); crear una
    sesion por operacion es algo mas lento pero inmune a ese problema.
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
                "Playwright no esta instalado. Ejecuta: pip install playwright && playwright install chromium"
            ) from exc

        self.settings = settings or Settings()
        self.timeout_ms = timeout_ms or int(self.settings.timeout * 1000)
        self.headless = headless
        self._deadline: float | None = None

    def _launch(self):
        """Abre una sesion nueva: (playwright, browser, context, page)."""
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=self.headless)
        context = browser.new_context(locale="es-ES", user_agent=self.USER_AGENT)
        page = context.new_page()
        return playwright, browser, context, page

    @staticmethod
    def _teardown(playwright, browser, context) -> None:
        """Cierra la sesion de forma sincrona y silenciosa.

        Un fallo al cerrar no debe propagarse: la sesion se descarta y el
        driver de Chromium se recicla con la siguiente operacion.
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
        """Fija un limite duro de tiempo (desde ahora) para todas las llamadas."""
        import time

        self._deadline = (time.monotonic() + seconds) if seconds else None

    def _expired(self) -> bool:
        import time

        return self._deadline is not None and time.monotonic() > self._deadline

    def _budget_ms(self, requested: int) -> int:
        """Recorta el timeout para no pasarse del deadline global.

        Nunca devuelve 0: en Playwright ``timeout=0`` significa *sin limite*
        (infinito), lo que provocaria un cuelgue. Si no queda presupuesto se
        devuelve el minimo (500 ms) para que la operacion falle rapido.
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
            text = text[:limit] + "\n<!-- truncado por max_browser_bytes -->"
        return BrowserPage(url=url, status=status, text=text)

    def get(self, url: str, *, wait_ms: int = 2500, **_ignored: object) -> BrowserPage:
        if self._expired():
            return BrowserPage(url=url, status=0, text="<!-- presupuesto de tiempo agotado -->")
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
        """Navega y espera a que aparezca `marker` en el HTML (o hasta `max_ms`).

        Util en buscadores que primero pintan un estado de carga/pool y luego
        reemplazan el contenido con los resultados reales de la consulta.
        """
        if self._expired():
            return BrowserPage(url=url, status=0, text="<!-- presupuesto de tiempo agotado -->")
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
        """No-op: cada operacion abre y cierra su propia sesion."""
        return None

    def __enter__(self) -> "BrowserFetcher":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
