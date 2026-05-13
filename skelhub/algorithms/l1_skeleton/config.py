"""Configuration for the L1-medial skeleton backend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class L1SkeletonConfig:
    """Validated parameters for the Python-native L1 skeleton backend."""

    sample_count: int = 512
    initial_radius: float | None = None
    radius_growth: float = 1.5
    max_radius: float | None = None
    max_iterations: int = 80
    stop_error: float = 0.01
    repulsion_mu: float = 0.35
    repulsion_mu_min: float = 0.15
    random_seed: int = 0

    def validate(self) -> "L1SkeletonConfig":
        """Validate config values and return self for chaining."""
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive.")
        if self.initial_radius is not None and self.initial_radius <= 0.0:
            raise ValueError("initial_radius must be positive when provided.")
        if self.radius_growth <= 1.0:
            raise ValueError("radius_growth must be greater than 1.0.")
        if self.max_radius is not None and self.max_radius <= 0.0:
            raise ValueError("max_radius must be positive when provided.")
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive.")
        if self.stop_error < 0.0:
            raise ValueError("stop_error must be non-negative.")
        if self.repulsion_mu < 0.0:
            raise ValueError("repulsion_mu must be non-negative.")
        if self.repulsion_mu_min < 0.0:
            raise ValueError("repulsion_mu_min must be non-negative.")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative.")
        return self
