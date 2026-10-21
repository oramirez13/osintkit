"""osintkit: OSINT and web scraping toolkit for public sources."""

__version__ = "0.2.0"

from .core import Result, Module, ModuleRegistry, registry
from .config import Settings
from .http import Fetcher
from .storage import Recorder
from .report import build_report, write_report

__all__ = [
    "__version__",
    "Result",
    "Module",
    "ModuleRegistry",
    "registry",
    "Settings",
    "Fetcher",
    "Recorder",
    "build_report",
    "write_report",
]
