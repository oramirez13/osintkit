"""Menu interactivo de osintkit.

Se lanza cuando se ejecuta ``osintkit`` sin argumentos. Ofrece las mismas
funciones que la linea de comandos, pidiendo los datos de forma guiada.
"""

from __future__ import annotations

import shlex
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import __version__

console = Console()

TITLE = "osintkit"
SUBTITLE = f"v{__version__} - toolkit de OSINT y webscraping para fuentes publicas"

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
    table.add_row("1", "Buscar una persona (nombre, telefono, id, email, nickname)")
    table.add_row("2", "Reconocimiento pasivo de un dominio")
    table.add_row("3", "Rastrear un sitio (crawl)")
    table.add_row("4", "Scrapear una URL con un YAML")
    table.add_row("5", "Regenerar informe HTML desde un JSONL")
    table.add_row("h", "Ayuda de comandos")
    table.add_row("q", "Salir")
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
    Prompt.ask("[dim]Enter para volver al menu[/]", default="")


def _action_search() -> None:
    value = Prompt.ask("[cyan]Dato a buscar[/] (puedes combinar con '+' ej: Nombre Apellido+empresa)")
    if not value.strip():
        return
    extra = Prompt.ask("[cyan]Opciones extra[/] (ej: '--browser --report', vacio = ninguna)", default="")
    argv = ["search", value, *_as_kwargs(extra)]
    if "--report" not in argv:
        console.print("[dim]sugerencia: agrega --report para generar el HTML[/]")
    _run("Busqueda web", _dispatch, argv)


def _action_domain() -> None:
    domains = Prompt.ask("[cyan]Dominio(s)[/] (separados por espacio)")
    if not domains.strip():
        return
    extra = Prompt.ask("[cyan]Opciones extra[/] (ej: '--report', vacio = ninguna)", default="")
    _run("Reconocimiento de dominio", _dispatch, ["domain", *domains.split(), *_as_kwargs(extra)])


def _action_crawl() -> None:
    url = Prompt.ask("[cyan]URL de inicio[/]")
    if not url.strip():
        return
    extra = Prompt.ask("[cyan]Opciones extra[/] (ej: '--depth 2 --max-pages 30 --report')", default="")
    _run("Rastreo de sitio", _dispatch, ["crawl", url, *_as_kwargs(extra)])


def _action_scrape() -> None:
    config = Prompt.ask("[cyan]Ruta del YAML[/]", default="examples/example_scrape.yaml")
    extra = Prompt.ask("[cyan]Opciones extra[/] (ej: '--report', vacio = ninguna)", default="")
    _run("Scraping", _dispatch, ["scrape", config, *_as_kwargs(extra)])


def _action_report() -> None:
    js = Prompt.ask("[cyan]Archivo JSONL[/]")
    if not js.strip():
        return
    title = Prompt.ask("[cyan]Titulo[/] (opcional)", default="")
    argv = ["report", js]
    if title.strip():
        argv += ["--title", title]
    _run("Informe HTML", _dispatch, argv)


def _action_help() -> None:
    _run("Ayuda", _dispatch, ["--help"])


def _dispatch(argv: list[str]) -> int:
    from .cli import main

    return main(argv)


ACTIONS: dict[str, tuple[str, Callable[[], None]]] = {
    "1": ("Buscar una persona", _action_search),
    "2": ("Reconocimiento de dominio", _action_domain),
    "3": ("Rastrear un sitio", _action_crawl),
    "4": ("Scrapear una URL", _action_scrape),
    "5": ("Regenerar informe HTML", _action_report),
    "h": ("Ayuda", _action_help),
}


def run_menu() -> int:
    """Bucle principal del menu interactivo."""
    while True:
        _print_banner()
        _menu_table()
        choice = Prompt.ask("[bold cyan]Elige una opcion[/]", default="q").strip().lower()
        if choice in ("q", "quit", "exit", "salir"):
            console.print("[cyan]Hasta luego.[/]")
            return 0
        action = ACTIONS.get(choice)
        if action is None:
            console.print("[red]Opcion no valida.[/]")
            Prompt.ask("[dim]Enter para continuar[/]", default="")
            continue
        _, func = action
        func()
