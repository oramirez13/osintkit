"""Scraping configurable por selectores CSS o XPath."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

try:
    from lxml import etree  # type: ignore
except ImportError:  # pragma: no cover - lxml es optional
    etree = None

from ..http import Fetcher


@dataclass
class FieldSpec:
    """Un campo a extraer de la página."""

    name: str
    selector: str
    attr: str | None = None
    all: bool = False
    default: str | None = None


@dataclass
class ScrapeSpec:
    """Definición declarativa de un scraping (idealmente cargada de YAML)."""

    url: str
    fields: list[FieldSpec] = field(default_factory=list)
    container: str | None = None
    mode: str = "css"
    encoding: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScrapeSpec":
        fields = [FieldSpec(**f) for f in data.get("fields", [])]
        return cls(
            url=data["url"],
            fields=fields,
            container=data.get("container"),
            mode=data.get("mode", "css"),
            encoding=data.get("encoding"),
        )


def _extract_node(node: Any, spec: FieldSpec) -> str | None:
    found = node
    if spec.attr:
        found = node.get(spec.attr)
    else:
        found = node.get_text(strip=True)
    return found if found else spec.default


def _extract_css(html: str, spec: ScrapeSpec) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(spec.container) if spec.container else [soup]
    rows: list[dict[str, Any]] = []
    for container in containers:
        row: dict[str, Any] = {}
        for field in spec.fields:
            if field.all:
                nodes = container.select(field.selector)
                row[field.name] = [v for v in (_extract_node(n, field) for n in nodes) if v is not None]
            else:
                node = container.select_one(field.selector)
                row[field.name] = _extract_node(node, field) if node is not None else field.default
        rows.append(row)
    return rows


def _extract_xpath(html: str, spec: ScrapeSpec) -> list[dict[str, Any]]:
    if etree is None:
        raise RuntimeError("lxml no está instalado; usa mode='css' o instala lxml")
    tree = etree.HTML(html)
    containers = tree.xpath(spec.container) if spec.container else [tree]
    rows: list[dict[str, Any]] = []
    for container in containers:
        row: dict[str, Any] = {}
        for field in spec.fields:
            nodes = container.xpath(field.selector)
            if field.all:
                row[field.name] = [
                    (n if iyesnstance(n, str) else (n.get(field.attr) if field.attr else n.text_content().strip() or None))
                    for n in nodes
                ]
            else:
                if not nodes:
                    row[field.name] = field.default
                    continue
                node = nodes[0]
                if field.attr:
                    row[field.name] = node.get(field.attr)
                else:
                    row[field.name] = node if iyesnstance(node, str) else (node.text_content().strip() or field.default)
        rows.append(row)
    return rows


def scrape_url(fetcher: Fetcher, spec: ScrapeSpec) -> list[dict[str, Any]]:
    """Descarga la URL y extrae los campos definidos."""
    response = fetcher.get(spec.url)
    if not response.ok:
        return [{"url": spec.url, "error": f"HTTP {response.status}", "status": response.status}]

    html = response.text
    rows = _extract_xpath(html, spec) if spec.mode == "xpath" else _extract_css(html, spec)
    for row in rows:
        row.setdefault("source_url", spec.url)
    return rows
