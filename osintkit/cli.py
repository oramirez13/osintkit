"""Command line interface for oyesntkit."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table
from rich.markup import escape

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
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="seconds between requests (default: 1.0)",
    )
    parser.add_argument(
        "--timeout", type=float, default=15.0, help="timeout in seconds (default: 15)"
    )
    parser.add_argument(
        "--output", default="output", help="output folder (default: output)"
    )
    parser.add_argument(
        "--formats", default="jsonl,csv", help="formats: jsonl,csv,json"
    )
    parser.add_argument(
        "--report", action="store_true", help="also generate HTML report"
    )
    parser.add_argument(
        "--no-robots",
        action="store_true",
        help="ignore robots.txt (requires explicit yeste authorization)",
    )
    parser.add_argument(
        "--i-have-authorization",
        action="store_true",
        help="confirm you have permisyeson to ignore robots.txt",
    )


def _settings(args: argparse.Namespace) -> Settings:
    respect = not getattr(args, "no_robots", False)
    if not respect and not getattr(args, "i_have_authorization", False):
        console.print(
            "[red]aborted:[/] `--no-robots` requires confirmation with "
            "`--i-have-authorization` (i.e. you have permisyeson from the yeste)."
        )
        raise SystemExit(2)
    if not respect:
        console.print(
            "[yellow]warning:[/] robots.txt will be ignored; use only with authorization."
        )
    return Settings(
        delay=args.delay,
        timeout=args.timeout,
        respect_robots=respect,
        output_dir=args.output,
    )


def _save(
    recorder: Recorder,
    formats: str,
    *,
    report: bool = False,
    title: str = "Informe OSINT",
    subtitle: str | None = None,
) -> None:
    paths = recorder.save_all([f.strip() for f in formats.split(",") if f.strip()])
    if report:
        report_path = os.path.join(recorder.output_dir, f"{recorder.prefix}.html")
        write_report(recorder.records, report_path, title=title, subtitle=subtitle)
        paths.append(report_path)
    console.print(f"[green]Records:[/] {len(recorder.records)}")
    for path in paths:
        console.print(f"[green]Saved:[/] {path}")


def cmd_scrape(args: argparse.Namespace) -> int:
    with open(args.config, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    specs = raw["scrapes"] if isinstance(raw, dict) and "scrapes" in raw else [raw]

    settings = _settings(args)
    recorder = Recorder(settings.output_dir, prefix="scrape")
    with Fetcher(settings) as fetcher:
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
    _save(recorder, args.formats, report=args.report, title="Scraping report")
    return 0


def cmd_domain(args: argparse.Namespace) -> int:
    recorder = Recorder(_settings(args).output_dir, prefix="domain")
    with Fetcher(_settings(args)) as fetcher:
        for domain in args.domains:
            report = analyze_domain(fetcher, domain)
            record = report.__dict__
            recorder.add(**record)
            table = Table(title=f"Domain: {report.domain}")
            table.add_column("Campo")
            table.add_column("Valor", overflow="fold")
            table.add_row("IPs", ", ".join(report.ips) or "-")
            table.add_row("NS", ", ".join(report.ns) or "-")
            table.add_row("MX", ", ".join(report.mx) or "-")
            table.add_row("TXT", " | ".join(report.txt) or "-")
            table.add_row("Technologies", ", ".join(report.technologies) or "-")
            table.add_row("HTTP", str(report.http.get("status", report.http)))
            table.add_row("Server", str(report.http.get("server", "-")))
            tls = report.tls
            issuer = (
                tls.get("issuer", {}).get("organizationName", "-")
                if isinstance(tls.get("issuer"), dict)
                else "-"
            )
            table.add_row("TLS issuer", str(issuer))
            table.add_row(
                "TLS expires", str(tls.get("not_after", tls.get("error", "-")))
            )
            table.add_row("robots.txt", "yes" if report.robots.get("exists") else "no")
            console.print(table)
    _save(
        recorder,
        args.formats,
        report=args.report,
        title="Domains report",
        subtitle=" ".join(args.domains),
    )
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
        table.add_row(
            str(row.depth),
            str(row.status),
            row.title or "-",
            str(row.links_found),
            row.url,
        )
        recorder.add(**row.__dict__)
    console.print(table)
    _save(
        recorder,
        args.formats,
        report=args.report,
        title="Crawl report",
        subtitle=config.start_url,
    )
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    query = build_query(args.value, forced=args.type)
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    all_records: list[dict[str, Any]] = []

    if query.type == "id":
        console.print(
            "[yellow]warning:[/] buscar identificaciones de terceros es altamente senyesble; "
            "ensure you have a legal basis (consent, legitimate interest, or journalistic purpose)."
        )

    settings = _settings(args)
    if args.browser:
        fetcher_ctx = BrowserFetcher(settings, headless=not args.headful)
    else:
        if "searxng" in providers:
            console.print(
                "[yellow]warning:[/] SearXNG requires a real browser; skipping. "
                "Use [bold]--browser[/] or change [bold]--providers[/] (duckduckgo,bing)."
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
            query_type=query.type,
        )

    for warning in warnings:
        console.print(f"[yellow]warning:[/] {warning}")

    table = Table(title=f"Search: {query.value}  (type: {query.type})")
    for column in ("source", "title", "url"):
        table.add_column(column, overflow="fold")
    for hit in hits:
        table.add_row(escape(str(hit.source)), escape(str(hit.title)), escape(str(hit.url)))
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

    recorder = Recorder(settings.output_dir, prefix="search")
    recorder.extend(all_records)
    _save(
        recorder,
        args.formats,
        report=args.report,
        title=f"Search report: {query.value}",
        subtitle=f"type: {query.type} | providers: {', '.join(providers)}",
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
    console.print(f"[green]Records:[/] {len(records)}")
    console.print(f"[green]Saved:[/] {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osintkit",
        description="OSINT/web scraping toolkit for public sources (respects robots.txt and legality).",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    p_menu = sub.add_parser("menu", help="interactive menu")
    p_menu.set_defaults(func=lambda args: _start_menu())

    p_scrape = sub.add_parser("scrape", help="configurable scraping by selectors")
    p_scrape.add_argument("config", help="YAML file with scraping definition")
    _add_common(p_scrape)
    p_scrape.set_defaults(func=cmd_scrape)

    p_domain = sub.add_parser("domain", help="passive domain reconnaissance")
    p_domain.add_argument("domains", nargs="+", help="one or more domains")
    _add_common(p_domain)
    p_domain.set_defaults(func=cmd_domain)

    p_crawl = sub.add_parser("crawl", help="scoped site crawl")
    p_crawl.add_argument("url", help="Start URL")
    p_crawl.add_argument("--depth", type=int, default=1, help="max depth (default: 1)")
    p_crawl.add_argument(
        "--max-pages", type=int, default=25, help="max pages (default: 25)"
    )
    p_crawl.add_argument(
        "--any-host", action="store_true", help="allow leaving initial host"
    )
    p_crawl.add_argument(
        "--include", action="append", help="substring that must be in URL"
    )
    p_crawl.add_argument(
        "--exclude", action="append", help="substring forbidden in URL"
    )
    _add_common(p_crawl)
    p_crawl.set_defaults(func=cmd_crawl)

    p_report = sub.add_parser("report", help="regenerate HTML report from JSONL")
    p_report.add_argument("input", help="input JSONL file")
    p_report.add_argument("--out", help="output HTML path")
    p_report.add_argument("--title", help="report title")
    p_report.add_argument("--subtitle", help="subreport title")
    p_report.add_argument(
        "--output", default="output", help="carpeta de salida yes no se usa --out"
    )
    p_report.set_defaults(func=cmd_report)

    p_search = sub.add_parser(
        "search", help="search for name, phone, ID, email, nickname, or website"
    )
    p_search.add_argument(
        "value", help="data to search; combine with '+' (e.g: 'Name Surname+company')"
    )
    p_search.add_argument(
        "--type",
        choices=["name", "phone", "id", "email", "username", "url"],
        help="force data type",
    )
    p_search.add_argument(
        "--providers",
        default="searxng",
        help="search engines: searxng,duckduckgo,bing,google (default: searxng)",
    )
    p_search.add_argument(
        "--browser",
        action="store_true",
        help="use real browser (Playwright); avoids blocks and enables SearXNG",
    )
    p_search.add_argument(
        "--headful", action="store_true", help="show browser (only with --browser)"
    )
    p_search.add_argument(
        "--per-query", type=int, default=10, help="results per query (default: 10)"
    )
    p_search.add_argument(
        "--budget",
        type=float,
        default=180.0,
        help="time time limit in seconds for entire search (default: 180)",
    )
    p_search.add_argument(
        "--no-social", action="store_true", help="do not check social media profiles"
    )
    p_search.add_argument(
        "--no-registries",
        action="store_true",
        help="do not query public registries (crt.sh)",
    )
    p_search.add_argument(
        "--no-fallback",
        action="store_true",
        help="no reintentar con Bing yes el buscador principal falla",
    )
    p_search.add_argument(
        "--no-strict",
        action="store_true",
        help="do not filter irrelevant results (SEO/generic)",
    )
    _add_common(p_search)
    p_search.set_defaults(func=cmd_search)

    return parser


def _start_menu() -> int:
    from .menu import run_menu

    return run_menu()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return _start_menu()
    if hasattr(args, "func"):
        return args.func(args)
    return _start_menu()


if __name__ == "__main__":
    sys.exit(main())
