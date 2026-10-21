"""Core utilities and base classes for osintkit modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Result:
    """Base result class for module outputs."""
    data: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Module(Protocol):
    """Protocol for osintkit modules."""
    name: str
    
    def run(self, *args, **kwargs) -> Result:
        """Execute module and return results."""
        ...
    
    def validate(self, *args, **kwargs) -> bool:
        """Validate inputs before execution."""
        ...


class ModuleRegistry:
    """Registry for available modules."""
    
    def __init__(self):
        self._modules: dict[str, type[Module]] = {}
    
    def register(self, name: str, module_cls: type[Module]) -> None:
        """Register a module class."""
        self._modules[name] = module_cls
    
    def get(self, name: str) -> type[Module] | None:
        """Get a module class by name."""
        return self._modules.get(name)
    
    def list_modules(self) -> list[str]:
        """List all registered module names."""
        return list(self._modules.keys())
    
    def create(self, name: str, *args, **kwargs) -> Module | None:
        """Create an instance of a registered module."""
        cls = self.get(name)
        if cls:
            return cls(*args, **kwargs)
        return None


# Global registry instance
registry = ModuleRegistry()
