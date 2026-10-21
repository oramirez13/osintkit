"""Configuración global y utilidades del toolkit."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

USER_AGENT_TOOL = "osintkit/0.1 (+osint; respeta robots.txt y ToS)"


@dataclass
class Settings:
    """Ajustes de ejecución compartidos por todos los módulos."""

    user_agent: str = USER_AGENT_TOOL
    timeout: float = 15.0
    delay: float = 1.0
    retries: int = 2
    max_bytes: int = 2_000_000
    respect_robots: bool = True
    output_dir: str = field(default_factory=lambda: os.environ.get("OSINTKIT_OUT", "output"))
    proxy: str | None = field(default_factory=lambda: os.environ.get("OSINTKIT_PROXY"))
    allow_insecure_proxy: bool = field(
        default_factory=lambda: os.environ.get("OSINTKIT_ALLOW_INSECURE_PROXY") == "1"
    )
    max_browser_bytes: int = 5_000_000
