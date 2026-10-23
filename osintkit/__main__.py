"""Punto de entrada del paquete."""

from .cli import main

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
