"""Flux-driven medial curve backend configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FluxConfig:
    """Validated runtime parameters for flux-driven medial curve extraction."""

    threshold: float = 0.0
    sigma: float = 0.5
    sigma_unit: str = "physical"

    def validate(self) -> "FluxConfig":
        """Validate config values and return self for chaining."""
        if self.sigma < 0.0:
            raise ValueError("sigma must be non-negative.")
        if self.sigma_unit not in {"physical", "voxels"}:
            raise ValueError("sigma_unit must be either 'physical' or 'voxels'.")
        return self
