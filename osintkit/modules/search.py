"""Busqueda OSINT por nombre, telefono, identificacion o nickname.

Fuentes soportadas:
  - DuckDuckGo (HTML, sin API key)
  - Bing (HTML)
  - Google Programmable Search (requiere API key + CX)
  - Registros publicos (crt.sh por dominio/email)
  - Redes sociales (perfiles publicos por nickname)

Todas consultan exclusivamente informacion publica. El usuario es responsable
de respetar los terminos de servicio y la legislacion aplicable.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

from ..http import Fetcher

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

PROVIDER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


@dataclass
class Hit:
    """Un resultado individual de busqueda."""

    title: str
    url: str
    snippet: str = ""
    source: str = ""
    query: str = ""


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


_STOPWORDS = {
    "and", "or", "the", "con", "para", "del", "los", "las", "una", "por",
    "que", "como", "perfil", "perfiles", "linkedin", "email", "contacto",
    "usuario", "social", "www", "com", "http", "https",
}

# Recordar la ultima instancia de SearXNG que funciono para probarla primero.
_SEARXNG_LAST_OK: list[str] = []


def _searxng_get(fetcher: "Fetcher", url: str, marker: str | None = None):
    """Descarga una pagina de SearXNG; con navegador espera a resultados reales.

    Las instancias lentas muestran primero un HTML con resultados precargados
    (pool) o de otra consulta; se espera a que el DOM contenga un termino de la
    consulta (`marker`) antes de leer. Si tras la primera espera no hay
    resultados, se reintenta una vez con mas margen: muchas instancias tardan en
    que el backend responda y la primera lectura coge el estado de carga.
    """
    if fetcher.__class__.__name__ != "BrowserFetcher":
        return fetcher.get(url, user_agent=PROVIDER_USER_AGENT)

    page = fetcher.get_ready(url, marker=marker, settle_ms=1200, max_ms=6000)
    # Si no aparecio el marcador ni hay tarjetas de resultado, reintenta con
    # mas margen (la instancia puede haber devuelto el pool o el estado inicial).
    if marker and _count_articles(page.text) == 0:
        retry = fetcher.get_ready(url, marker=marker, settle_ms=1500, max_ms=9000)
        if _count_articles(retry.text) >= _count_articles(page.text):
            page = retry
    return page


def _count_articles(html: str) -> int:
    """Cuenta tarjetas de resultado en el HTML de SearXNG (rapido, sin BS4)."""
    return html.lower().count("article") + html.lower().count('class="result')


def _fold(text: str) -> str:
    """Minusculas sin acentos, para comparar de forma robusta."""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _relevant(hit: "Hit", terms: list[str], *, min_match: int = 1) -> bool:
    """True si el resultado contiene al menos `min_match` terminos del valor buscado.

    Evita reportar resultados genericos que los buscadores devuelven cuando no
    encuentran coincidencias exactas. Cada termino compuesto ("Nombre Apellido")
    se evalua por sus palabras internas, no como frase literal.
    """
    needle = _fold(" ".join([hit.title, hit.url, hit.snippet]))

    def _matched(term: str) -> bool:
        words = [w for w in _fold(term).split() if len(w) >= 4]
        if not words:
            return True
        # El termino cuenta si aparece la mayoria de sus palabras.
        hits = sum(1 for w in words if w in needle)
        return hits >= max(1, (len(words) + 1) // 2)

    distinct = [t for t in terms if len(t) >= 3]
    if not distinct:
        return True
    return sum(1 for t in distinct if _matched(t)) >= min_match


def _ddg_unwrap(href: str) -> str:
    """DuckDuckGo envuelve algunos enlaces en /l/?uddg=...; extrae el destino."""
    match = re.search(r"[?&]uddg=([^&]+)", href)
    if match:
        return unquote(match.group(1))
    if href.startswith("//"):
        return "https:" + href
    return href


def _bing_unwrap(href: str) -> str:
    """Bing envuelve los enlaces en https://www.bing.com/ck/a?...&u=a1<base64>."""
    parsed = urlparse(href)
    if "bing.com" not in parsed.netloc or "/ck/a" not in parsed.path:
        return href
    params = parse_qs(parsed.query)
    raw = params.get("u", [""])[0]
    if raw.startswith("a1"):
        raw = raw[2:]
    try:
        padded = raw + "=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", "replace")
    except Exception:
        return href


# ---------------------------------------------------------------------------
# Proveedores de buscador
# ---------------------------------------------------------------------------


def search_duckduckgo(fetcher: Fetcher, query: str, limit: int = 10) -> list[Hit]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    response = fetcher.get(url, use_cache=False, user_agent=PROVIDER_USER_AGENT)
    # DuckDuckGo responde 202 cuando aplica anti-bot/CAPTCHA temporal.
    if response.status != 200:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    hits: list[Hit] = []
    for node in soup.select(".result")[:limit]:
        link = node.select_one("a.result__a")
        if not link:
            continue
        snippet = node.select_one(".result__snippet")
        hits.append(
            Hit(
                title=_clean(link.get_text()),
                url=_ddg_unwrap(link.get("href", "")),
                snippet=_clean(snippet.get_text() if snippet else ""),
                source="duckduckgo",
                query=query,
            )
        )
    return hits


def search_bing(fetcher: Fetcher, query: str, limit: int = 10) -> list[Hit]:
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={limit}"
    response = fetcher.get(url, use_cache=False, user_agent=PROVIDER_USER_AGENT)
    if not response.ok:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    hits: list[Hit] = []
    for node in soup.select("li.b_algo")[:limit]:
        link = node.select_one("h2 a")
        if not link:
            continue
        snippet = node.select_one(".b_caption p") or node.select_one("p")
        hits.append(
            Hit(
                title=_clean(link.get_text()),
                url=_bing_unwrap(link.get("href", "")),
                snippet=_clean(snippet.get_text() if snippet else ""),
                source="bing",
                query=query,
            )
        )
    return hits


def search_searxng(fetcher: Fetcher, query: str, limit: int = 10) -> list[Hit]:
    """SearXNG (meta-buscador). Requiere un fetcher de navegador (Playwright).

    Se prueban varias instancias publicas, esperando a que carguen resultados
    reales y comprobando que sean relevantes para la consulta. Algunas
    instancias devuelven resultados precargados (pool) o de otra consulta si se
    leen antes de que el backend responda.
    """
    instances = os.environ.get(
        "SEARXNG_INSTANCES",
        "https://search.inetol.net,https://priv.au,https://searxng.site,https://searx.be",
    ).split(",")
    instances = [b.strip().rstrip("/") for b in instances if b.strip()]
    # Prioriza la instancia que funciono la ultima vez.
    instances.sort(key=lambda b: 0 if b in _SEARXNG_LAST_OK else 1)
    url_path = f"/search?q={quote_plus(query)}"
    # Terminos significativos de la consulta para validar relevancia.
    terms = [t for t in re.findall(r"[^\W_]{4,}", query) if t.lower() not in _STOPWORDS]
    marker = max(terms, key=len) if terms else None
    min_match = 2 if len(terms) >= 3 else 1
    best: list[Hit] = []
    for base in instances:
        response = _searxng_get(fetcher, base + url_path, marker=marker)
        if not response.ok:
            continue
        html = response.text
        if "captcha" in html.lower():
            continue
        soup = BeautifulSoup(html, "html.parser")
        hits: list[Hit] = []
        for node in soup.select("article.result, .result"):
            link = node.select_one("h3 a, a.url_wrapper, a")
            if not link or not link.get("href"):
                continue
            snippet = node.select_one("p.content, .content")
            hits.append(
                Hit(
                    title=_clean(link.get_text()),
                    url=link.get("href", ""),
                    snippet=_clean(snippet.get_text() if snippet else ""),
                    source="searxng",
                    query=query,
                )
            )
        relevant = [h for h in hits if _relevant(h, terms, min_match=min_match)]
        if relevant:
            if base not in _SEARXNG_LAST_OK:
                _SEARXNG_LAST_OK.insert(0, base)
            return relevant[:limit]
        if len(hits) > len(best):
            best = hits
    # Ninguna instancia dio resultados relevantes: mejor devolver [] que ruido.
    return [] if terms else best[:limit]


def search_google_cse(fetcher: Fetcher, query: str, limit: int = 10) -> list[Hit]:
    api_key = os.environ.get("GOOGLE_CSE_KEY")
    cx = os.environ.get("GOOGLE_CSE_CX")
    if not api_key or not cx:
        return []
    url = (
        "https://www.googleapis.com/customsearch/v1"
        f"?key={api_key}&cx={cx}&num={min(limit, 10)}&q={quote_plus(query)}"
    )
    response = fetcher.get(url, use_cache=False, user_agent=PROVIDER_USER_AGENT)
    if not response.ok:
        return []
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError:
        return []
    hits: list[Hit] = []
    for item in data.get("items", []):
        hits.append(
            Hit(
                title=_clean(item.get("title")),
                url=item.get("link", ""),
                snippet=_clean(item.get("snippet")),
                source="google",
                query=query,
            )
        )
    return hits


# ---------------------------------------------------------------------------
# Fuentes OSINT adicionales
# ---------------------------------------------------------------------------


def search_social(fetcher: Fetcher, username: str, limit: int = 10) -> list[Hit]:
    """Comprueba la existencia de perfiles publicos por nickname.

    Solo reporta un perfil si hay evidencia positiva especifica de la
    plataforma; un simple HTTP 200 no basta (muchas redes devuelven 200 con
    muro de login o pagina generica, lo que produce falsos positivos).
    """
    handle = username.lstrip("@")
    platforms = {
        "github": (f"https://github.com/{handle}", ("profile", handle.lower())),
        "twitter": (f"https://x.com/{handle}", (f"/{handle.lower()}",)),
        "instagram": (f"https://www.instagram.com/{handle}/", ('"username":"' + handle.lower(), f"/{handle.lower()}/")),
        "reddit": (f"https://www.reddit.com/user/{handle}", ("/user/" + handle.lower(),)),
        "tiktok": (f"https://www.tiktok.com/@{handle}", (f"/@{handle.lower()}",)),
        "keybase": (f"https://keybase.io/{handle}", (f"/{handle.lower()}",)),
    }
    negative = (
        "not found", "page not found", "no encontrado", "doesn't exist",
        "does not exist", "usuario no existe", "sorry, nobody on reddit",
        "page you were looking for", "couldn't find",
    )
    hits: list[Hit] = []
    for platform, (url, signals) in platforms.items():
        if len(hits) >= limit:
            break
        response = fetcher.get(url, use_cache=False, user_agent=PROVIDER_USER_AGENT)
        if response.status != 200:
            continue
        page = response.text.lower()
        if any(token in page for token in negative):
            continue
        # Evidencia positiva: alguna senal propia de la plataforma debe aparecer.
        if not any(sig.lower() in page for sig in signals):
            continue
        hits.append(
            Hit(
                title=f"Perfil en {platform}: {handle}",
                url=url,
                snippet=f"HTTP 200 y marcador de perfil presente en {platform}",
                source=f"social:{platform}",
                query=handle,
            )
        )

    # Telegram: solo hay perfil si la pagina trae un titulo no vacio.
    if len(hits) < limit:
        url = f"https://t.me/{handle}"
        response = fetcher.get(url, use_cache=False, user_agent=PROVIDER_USER_AGENT)
        if response.status == 200:
            match = re.search(r'tgme_page_title[^>]*>(.*?)</div>', response.text, re.S)
            title = re.sub(r"<[^>]+>", "", match.group(1)).strip() if match else ""
            if title:
                hits.append(
                    Hit(
                        title=f"Perfil en telegram: {handle}",
                        url=url,
                        snippet=f"pagina publica de Telegram: {title}",
                        source="social:telegram",
                        query=handle,
                    )
                )
    return hits


def search_crtsh(fetcher: Fetcher, term: str, limit: int = 20) -> list[Hit]:
    """Certificados publicos (crt.sh) por dominio; util si el dato es un dominio/email."""
    domain = term.split("@")[-1].lstrip("*.").strip()
    if "." not in domain:
        return []
    url = f"https://crt.sh/?q=%25.{quote_plus(domain)}&output=json"
    response = fetcher.get(url, use_cache=False, user_agent=PROVIDER_USER_AGENT)
    if not response.ok:
        return []
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError:
        return []
    seen: set[str] = set()
    hits: list[Hit] = []
    for entry in data:
        name = entry.get("name_value", "")
        for value in str(name).splitlines():
            value = value.strip().lower()
            if value and value not in seen:
                seen.add(value)
                hits.append(
                    Hit(
                        title=value,
                        url=f"https://{value}",
                        snippet="subdominio en certificado TLS publico (crt.sh)",
                        source="crtsh",
                        query=term,
                    )
                )
            if len(hits) >= limit:
                return hits
    return hits


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, Callable[[Fetcher, str, int], list[Hit]]] = {
    "searxng": search_searxng,
    "duckduckgo": search_duckduckgo,
    "bing": search_bing,
    "google": search_google_cse,
}

# Proveedores que degradan o bloquean clientes HTTP simples; con navegador
# (Playwright) funcionan mejor.
BROWSER_FIRST = {"searxng"}


@dataclass
class SearchResult:
    value: str
    type: str
    queries: list[str]
    hits: list[Hit] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def run_search(
    fetcher: Fetcher,
    queries: list[str],
    *,
    providers: list[str] | None = None,
    per_query: int = 10,
    include_social: bool = True,
    include_registries: bool = True,
    terms: list[str] | None = None,
    fallback: bool = True,
    strict: bool = True,
    budget: float | None = None,
) -> tuple[list[Hit], list[str]]:
    """Ejecuta las consultas en cada proveedor y agrega los resultados.

    Devuelve (hits, avisos). Si un proveedor no devuelve nada para una consulta
    y `fallback` esta activo, se intenta con Bing como respaldo. Con `strict`
    se descartan resultados que no contengan ninguna palabra del valor buscado.
    `budget` es un limite en segundos para toda la busqueda (evita cuelgues).
    """
    providers = providers or ["duckduckgo"]
    all_hits: list[Hit] = []
    warnings: list[str] = []
    seen_urls: set[str] = set()
    match_terms = [t for t in (terms or []) if len(t) >= 3]
    # El primer termino (dato principal) es obligatorio; los secundarios
    # (p. ej. la empresa en "Nombre+Empresa") solo refuerzan.
    primary_term = match_terms[0] if match_terms else None
    if len(match_terms) >= 2:
        min_match = 1
    else:
        min_match = 1
    can_browse = hasattr(fetcher, "get") and fetcher.__class__.__name__ == "BrowserFetcher"
    deadline = (time.monotonic() + budget) if budget else None
    if deadline is not None and hasattr(fetcher, "set_deadline"):
        fetcher.set_deadline(budget)

    def _expired() -> bool:
        return deadline is not None and time.monotonic() > deadline

    for query in queries:
        if _expired():
            warnings.append("presupuesto de tiempo agotado: se detuvo la busqueda antes de terminar.")
            break
        query_hits: list[Hit] = []
        for provider in providers:
            if _expired():
                break
            func = PROVIDERS.get(provider)
            if func is None:
                warnings.append(f"proveedor desconocido: {provider}")
                continue
            query_hits.extend(func(fetcher, query, per_query))

        # Respaldo: si nada funciono, probar otro proveedor que no este en uso.
        if not query_hits and fallback and not _expired():
            if "bing" not in providers:
                warnings.append(f"sin resultados en {','.join(providers)} para {query!r}; reintentando con Bing")
                query_hits.extend(search_bing(fetcher, query, per_query))
            elif can_browse and "searxng" not in providers:
                warnings.append(f"sin resultados en {','.join(providers)} para {query!r}; reintentando con SearXNG")
                query_hits.extend(search_searxng(fetcher, query, per_query))

        for hit in query_hits:
            if strict and primary_term and not _relevant(hit, [primary_term]):
                continue
            if hit.url and hit.url not in seen_urls:
                seen_urls.add(hit.url)
                all_hits.append(hit)

    if not all_hits:
        warnings.append(
            "sin resultados relevantes: los buscadores no devolvieron coincidencias para el valor (o se descarto ruido)."
        )

    primary = (terms or queries or [""])[0]
    if include_social and primary and not _expired() and re.match(r"^@?[A-Za-z0-9_.-]{2,30}$", primary):
        for hit in search_social(fetcher, primary, per_query):
            if hit.url not in seen_urls:
                seen_urls.add(hit.url)
                all_hits.append(hit)

    if include_registries and not _expired():
        for term in (terms or [])[:1]:
            for hit in search_crtsh(fetcher, term, per_query):
                if hit.url not in seen_urls:
                    seen_urls.add(hit.url)
                    all_hits.append(hit)

    return all_hits, warnings
