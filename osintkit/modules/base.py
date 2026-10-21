"""Base classes for modules."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..core import Result, Module


@dataclass
class BaseModuleConfig:
    """Base configuration for modules."""
    timeout: float = 15.0
    delay: float = 1.0
    retries: int = 2


class BaseModule(ABC):
    """Abstract base class for all modules."""
    
    name: str = "base"
    description: str = ""
    
    def __init__(self, fetcher=None, config: BaseModuleConfig | None = None):
        self.fetcher = fetcher
        self.config = config or BaseModuleConfig()
    
    @abstractmethod
    def run(self, *args, **kwargs) -> Result:
        """Execute the module."""
        pass
    
    def validate(self, *args, **kwargs) -> bool:
        """Validate inputs. Override if needed."""
        return True
    
    def _create_result(self, data: dict[str, Any] | None = None, 
                      success: bool = True, 
                      errors: list[str] | None = None) -> Result:
        """Helper to create Result objects."""
        return Result(
            data=data or {},
            success=success,
            errors=errors or [],
            metadata={"module": self.name}
        )
