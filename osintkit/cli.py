"""Interfaz de linea de comandos para osintkit."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

from .browser import BrowserFetcher
from .config import Settings
from .http import Fetcher
from .modules.crawl import CrawlConfig, crawl
from .modules.detect import build_query
from .modules.domain import analyze_domain
from .modules.scrape import ScrapeSpec, scrape_url
from .modules.search import run_search
from .report import write_report
from .storage import Recorder

console = Console()


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--delay", type=float, default=1.0, help="segundos entre peticiones (default: 1.0)")
    parser.add_argument("--timeout", type=float, default=15.0, help="timeout en segundos (default: 15)")
    parser.add_argument("--output", default="output", help="carpeta de salida (default: output)")
    parser.add_argument("--formats", default="jsonl,csv", help="formatos: jsonl,csv,json")
    parser.add_argument("--report", action="store_true", help="generar tambien un informe HTML")
    parser.add_argument("--no-robots", action="store_true", help="ignorar robots.txt (requiere autorizacion explicita del sitio)")
    parser.add_argument("--i-have-authorization", action="store_true", help="confirma que tienes permiso para ignorar robots.txt")


def _settings(args: argparse.Namespace) -> Settings:
    respect = not getattr(args, "no_robots", False)
    if not respect and not getattr(args, "i_have_authorization", False):
        console.print(
            "[red]abortado:[/] `--no-robots` requiere confirmar con "
            "`--i-have-authorization` (o sea, que tienes permiso del sitio)."
        )
        raise SystemExit(2)
    if not respect:
        console.print("[yellow]aviso:[/] se ignorara robots.txt; usa esto solo con autorizacion.")
    return Settings(
        delay=args.delay,
        timeout=args.timeout,
        respect_robots=respect,
        output_dir=args.output,
    )


def _save(recorder: Recorder, formats: str, *, report: bool = False, title: str = "Informe OSINT", subtitle: str | None = None) -> None:
    paths = recorder.save_all([f.strip() for f in formats.split(",") if f.strip()])
    if report:
        report_path = os.path.join(recorder.output_dir, f"{recorder.prefix}.html")
        write_report(recorder.records, report_path, title=title, subtitle=subtitle)
        paths.append(report_path)
    console.print(f"[green]Registros:[/] {len(recorder.records)}")
    for path in paths:
        console.print(f"[green]Guardado:[/] {path}")


def cmd_scrape(args: argparse.Namespace) -> int:
    with open(args.config, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    specs = raw["scrapes"] if isinstance(raw, dict) and "scrapes" in raw else [raw]

    recorder = Recorder(_settings(args).output_dir, prefix="scrape")
    with Fetcher(_settings(args)) as fetcher:
        for item in specs:
            spec = ScrapeSpec.from_dict(item)
            rows = scrape_url(fetcher, spec)
            table = Table(title=spec.url, show_lines=False)
            if rows:
                for column in rows[0]:
                    table.add_column(column, overflow="fold")
                for row in rows:
                    table.add_row(*[str(row.get(c, "")) for c in rows[0]])
            console.print(table)
            recorder.extend(rows)
    _save(recorder, args.formats, report=args.report, title="Informe de scraping")
    return 0


def cmd_domain(args: argparse.Namespace) -> int:
    recorder = Recorder(_settings(args).output_dir, prefix="domain")
    with Fetcher(_settings(args)) as fetcher:
        for domain in args.domains:
            report = analyze_domain(fetcher, domain)
            record = report.__dict__
            recorder.add(**record)
            table = Table(title=f"Dominio: {report.domain}")
            table.add_column("Campo")
            table.add_column("Valor", overflow="fold")
            table.add_row("IPs", ", ".join(report.ips) or "-")
            table.add_row("NS", ", ".join(report.ns) or "-")
            table.add_row("MX", ", ".join(report.mx) or "-")
            table.add_row("TXT", " | ".join(report.txt) or "-")
            table.add_row("Tecnologias", ", ".join(report.technologies) or "-")
            table.add_row("HTTP", str(report.http.get("status", report.http)))
            table.add_row("Server", str(report.http.get("server", "-")))
            tls = report.tls
            issuer = tls.get("issuer", {}).get("organizationName", "-") if isinstance(tls.get("issuer"), dict) else "-"
            table.add_row("TLS issuer", str(issuer))
            table.add_row("TLS expira", str(tls.get("not_after", tls.get("error", "-"))))
            table.add_row("robots.txt", "si" if report.robots.get("exists") else "no")
            console.print(table)
    _save(recorder, args.formats, report=args.report, title="Informe de dominios", subtitle=" ".join(args.domains))
    return 0


def cmd_crawl(args: argparse.Namespace) -> int:
    config = CrawlConfig(
        start_url=args.url,
        max_depth=args.depth,
        max_pages=args.max_pages,
        stay_on_host=not args.any_host,
        respect_robots=not args.no_robots,
        include=tuple(args.include or ()),
        exclude=tuple(args.exclude or ()),
    )
    recorder = Recorder(_settings(args).output_dir, prefix="crawl")
    with Fetcher(_settings(args)) as fetcher:
        results = crawl(fetcher, config)
    table = Table(title=f"Crawl: {config.start_url}")
    for column in ("depth", "status", "title", "links", "url"):
        table.add_column(column, overflow="fold")
    for row in results:
        table.add_row(str(row.depth), str(row.status), row.title or "-", str(row.links_found), row.url)
        recorder.add(**row.__dict__)
    console.print(table)
    _save(recorder, args.formats, report=args.report, title="Informe de rastreo", subtitle=config.start_url)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    query = build_query(args.value, forced=args.type)
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    all_records: list[dict[str, Any]] = []

    if query.type == "id":
        console.print(
            "[yellow]aviso:[/] buscar identificaciones de terceros es altamente sensible; "
            "asegurate de tener una base legal (consentimiento, interes legitimo o fin periodistico)."
        )

    settings = _settings(args)
    if args.browser:
        fetcher_ctx = BrowserFetcher(settings, headless=not args.headful)
    else:
        if "searxng" in providers:
            console.print(
                "[yellow]aviso:[/] SearXNG requiere navegador real; se omite. "
                "Usa [bold]--browser[/] o cambia [bold]--providers[/] (duckduckgo,bing)."
            )
            providers = [p for p in providers if p != "searxng"] or ["duckduckgo"]
        fetcher_ctx = Fetcher(settings)

    with fetcher_ctx as fetcher:
        hits, warnings = run_search(
            fetcher,
            query.queries,
            providers=providers,
            per_query=args.per_query,
            include_social=not args.no_social,
            include_registries=not args.no_registries,
            terms=query.terms,
            fallback=not args.no_fallback,
            strict=not args.no_strict,
            budget=args.budget,
        )

    for warning in warnings:
        console.print(f"[yellow]aviso:[/] {warning}")

    table = Table(title=f"Busqueda: {query.value}  (tipo: {query.type})")
    for column in ("source", "title", "url"):
        table.add_column(column, overflow="fold")
    for hit in hits:
        table.add_row(hit.source, hit.title, hit.url)
        all_records.append(
            {
                "type": query.type,
                "value": query.value,
                "source": hit.source,
                "title": hit.title,
                "url": hit.url,
                "snippet": hit.snippet,
                "query": hit.query,
            }
        )
    console.print(table)

    recorder = Recorder(_settings(args).output_dir, prefix="search")
    recorder.extend(all_records)
    _save(
        recorder,
        args.formats,
        report=args.report,
        title=f"Informe de busqueda: {query.value}",
        subtitle=f"tipo: {query.type} | proveedores: {', '.join(providers)}",
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    records: list[dict[str, Any]] = []
    with open(args.input, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    title = args.title or os.path.splitext(os.path.basename(args.input))[0]
    out_path = args.out or os.path.join(args.output, f"{title}.html")
    subtitle = args.subtitle
    write_report(records, out_path, title=title, subtitle=subtitle)
    console.print(f"[green]Registros:[/] {len(records)}")
    console.print(f"[green]Guardado:[/] {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osintkit",
        description="Toolkit de OSINT/webscraping para fuentes publicas (respeta robots.txt y la legalidad).",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    p_menu = sub.add_parser("menu", help="menu interactivo")
    p_menu.set_defaults(func=lambda args: _start_menu())

    p_scrape = sub.add_parser("scrape", help="scraping configurable por selectores")
    p_scrape.add_argument("config", help="archivo YAML con la definicion del scraping")
    _add_common(p_scrape)
    p_scrape.set_defaults(func=cmd_scrape)

    p_domain = sub.add_parser("domain", help="reconocimiento pasivo de dominios")
    p_domain.add_argument("domains", nargs="+", help="uno o mas dominios")
    _add_common(p_domain)
    p_domain.set_defaults(func=cmd_domain)

    p_crawl = sub.add_parser("crawl", help="rastreo acotado de un sitio")
    p_crawl.add_argument("url", help="URL de inicio")
    p_crawl.add_argument("--depth", type=int, default=1, help="profundidad maxima (default: 1)")
    p_crawl.add_argument("--max-pages", type=int, default=25, help="paginas maximas (default: 25)")
    p_crawl.add_argument("--any-host", action="store_true", help="permitir salir del host inicial")
    p_crawl.add_argument("--include", action="append", help="subcadena que debe estar en la URL")
    p_crawl.add_argument("--exclude", action="append", help="subcadena prohibida en la URL")
    _add_common(p_crawl)
    p_crawl.set_defaults(func=cmd_crawl)

    p_report = sub.add_parser("report", help="regenerar un informe HTML desde un JSONL")
    p_report.add_argument("input", help="archivo JSONL de entrada")
    p_report.add_argument("--out", help="ruta del HTML de salida")
    p_report.add_argument("--title", help="titulo del informe")
    p_report.add_argument("--subtitle", help="subtitulo del informe")
    p_report.add_argument("--output", default="output", help="carpeta de salida si no se usa --out")
    p_report.set_defaults(func=cmd_report)

    p_search = sub.add_parser("search", help="buscar un nombre, telefono, identificacion, email o nickname")
    p_search.add_argument("value", help="dato a buscar; combina varios con '+' (ej: 'Nombre Apellido+empresa')")
    p_search.add_argument("--type", choices=["name", "phone", "id", "email", "username"], help="forzar el tipo de dato")
    p_search.add_argument("--providers", default="searxng", help="buscadores: searxng,duckduckgo,bing,google (default: searxng)")
    p_search.add_argument("--browser", action="store_true", help="usar un navegador real (Playwright); evita bloqueos y activa SearXNG")
    p_search.add_argument("--headful", action="store_true", help="mostrar el navegador (solo con --browser)")
    p_search.add_argument("--per-query", type=int, default=10, help="resultados por consulta (default: 10)")
    p_search.add_argument("--budget", type=float, default=180.0, help="limite de segundos para toda la busqueda (default: 180)")
    p_search.add_argument("--no-social", action="store_true", help="no comprobar perfiles en redes sociales")
    p_search.add_argument("--no-registries", action="store_true", help="no consultar registros publicos (crt.sh)")
    p_search.add_argument("--no-fallback", action="store_true", help="no reintentar con Bing si el buscador principal falla")
    p_search.add_argument("--no-strict", action="store_true", help="no filtrar resultados irrelevantes (SEO/genericos)")
    _add_common(p_search)
    p_search.set_defaults(func=cmd_search)

    return parser


def _start_menu() -> int:
    from .menu import run_menu

    return run_menu()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, _unknown = parser.parse_known_args(argv)
    if args.command is None:
        return _start_menu()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
