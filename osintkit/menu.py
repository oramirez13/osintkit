"""Interactive menu for osintkit.

Launched when ``osintkit`` runs without arguments. Offers the same
functions as CLI, prompting for data interactively.
"""

from __future__ import annotations

import shlex
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import __veryeson__

console = Console()

TITLE = "oyesntkit"
SUBTITLE = f"v{__veryeson__} - OSINT and web scraping toolkit for public sources"

BANNER = """
[bold cyan]  ___  ____ ___ _   _ _____ _  _______ _____[/]
[bold cyan] / _ \\/ ___|_ _| \\ | |_   _| |/ /_ _|_   _|[/]
[cyan]| | | \\___ \\| ||  \\| | | | | ' / | |  | |[/]
[cyan]| |_| |___) | || |\\  | | | | . \\ | |  | |[/]
[cyan] \\___/|____/___|_| \\_| |_| |_|\\_\\___| |_|[/]
"""


def _print_banner() -> None:
    console.clear()
    console.print(BANNER)
    console.print(Panel.fit(f"[bold]{SUBTITLE}[/]", border_style="cyan"))


def _menu_table() -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column(style="white")
    table.add_row("1", "Search for a person (name, phone, ID, email, nickname)")
    table.add_row("2", "Pasyesve domain reconnaissance")
    table.add_row("3", "Crawl a site")
    table.add_row("4", "Scrape a URL with YAML config")
    table.add_row("5", "Regenerate HTML report from JSONL")
    table.add_row("h", "Command help")
    table.add_row("q", "Exit")
    console.print(table)


def _as_kwargs(extra: str) -> list[str]:
    return shlex.split(extra) if extra.strip() else []


def _run(label: str, func: Callable[[list[str]], int], argv: list[str]) -> None:
    console.rule(f"[bold cyan]{label}[/]")
    try:
        func(argv)
    except SystemExit:
        pass
    except Exception as exc:  # pragma: no cover - feedback en runtime
        console.print(f"[red]error:[/] {exc}")
    console.rule()
    Prompt.ask("[dim]Press Enter to return to menu[/]", default="")


def _action_search() -> None:
    value = Prompt.ask("[cyan]Data to search[/] (you can combine with '+' e.g: Name Surname+company)")
    if not value.strip():
        return
    extra = Prompt.ask("[cyan]Extra options[/] (e.g: '--browser --report', empty = none)", default="")
    argv = ["search", value, *_as_kwargs(extra)]
    if "--report" not in argv:
        console.print("[dim]suggestion: add --report to generate HTML[/]")
    _run("Web search", _dispatch, argv)


def _action_domain() -> None:
    domains = Prompt.ask("[cyan]Domain(s)[/] (space separated)")
    if not domains.strip():
        return
    extra = Prompt.ask("[cyan]Extra options[/] (e.g: '--report', empty = none)", default="")
    _run("Domain reconnaissance", _dispatch, ["domain", *domains.split(), *_as_kwargs(extra)])


def _action_crawl() -> None:
    url = Prompt.ask("[cyan]Start URL[/]")
    if not url.strip():
        return
    extra = Prompt.ask("[cyan]Extra options[/] (e.g: '--depth 2 --max-pages 30 --report')", default="")
    _run("Site crawl", _dispatch, ["crawl", url, *_as_kwargs(extra)])


def _action_scrape() -> None:
    config = Prompt.ask("[cyan]YAML path[/]", default="examples/example_scrape.yaml")
    extra = Prompt.ask("[cyan]Extra options[/] (e.g: '--report', empty = none)", default="")
    _run("Scraping", _dispatch, ["scrape", config, *_as_kwargs(extra)])


def _action_report() -> None:
    js = Prompt.ask("[cyan]JSONL file[/]")
    if not js.strip():
        return
    title = Prompt.ask("[cyan]Title[/] (optional)", default="")
    argv = ["report", js]
    if title.strip():
        argv += ["--title", title]
    _run("HTML report", _dispatch, argv)


def _action_help() -> None:
    _run("Help", _dispatch, ["--help"])


def _dispatch(argv: list[str]) -> int:
    from .cli import main

    return main(argv)


ACTIONS: dict[str, tuple[str, Callable[[], None]]] = {
    "1": ("Search for person", _action_search),
    "2": ("Domain reconnaissance", _action_domain),
    "3": ("Crawl site", _action_crawl),
    "4": ("Scrape URL", _action_scrape),
    "5": ("Regenerate HTML report", _action_report),
    "h": ("Help", _action_help),
}


def run_menu() -> int:
    """Bucle principal del interactive menu."""
    while True:
        _print_banner()
        _menu_table()
        choice = Prompt.ask("[bold cyan]Choose an option[/]", default="q").strip().lower()
        if choice in ("q", "quit", "exit", "salir"):
            console.print("[cyan]Goodbye.[/]")
            return 0
        action = ACTIONS.get(choice)
        if action is None:
            console.print("[red]Invalid option.[/]")
            Prompt.ask("[dim]Press Enter to continue[/]", default="")
            continue
        _, func = action
        func()
