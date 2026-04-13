"""MCP backend configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MCPConfig:
    """Validated MCP runtime parameters exposed at the framework layer."""

    root_method: str = "max_fdt"
    threshold_scale: float = 1.0
    dilation_factor: float = 2.0
    max_iterations: int = 200
    min_object_size: int = 50
    label_objects: bool = False

    def validate(self) -> "MCPConfig":
        """Validate config values and return self for chaining."""
        if self.root_method not in {"max_fdt", "topmost"}:
            raise ValueError("root_method must be 'max_fdt' or 'topmost'.")
        if self.threshold_scale <= 0.0:
            raise ValueError("threshold_scale must be positive.")
        if self.dilation_factor <= 0.0:
            raise ValueError("dilation_factor must be positive.")
        if self.max_iterations < 0:
            raise ValueError("max_iterations must be non-negative.")
        if self.min_object_size < 0:
            raise ValueError("min_object_size must be non-negative.")
        return self
