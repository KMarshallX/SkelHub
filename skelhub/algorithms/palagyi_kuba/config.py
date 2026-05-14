"""Palagyi-Kuba backend configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PalagyiKubaConfig:
    """Validated runtime parameters for Palagyi-Kuba thinning."""

    mode: str = "curve"
    binarize_threshold: float = 0.5
    max_cycles: int | None = None

    def validate(self) -> "PalagyiKubaConfig":
        """Validate config values and return self for chaining."""
        if self.mode not in {"curve", "surface"}:
            raise ValueError("mode must be either 'curve' or 'surface'.")
        if not (0.0 <= self.binarize_threshold <= 1.0):
            raise ValueError("binarize_threshold must be between 0.0 and 1.0.")
        if self.max_cycles is not None and self.max_cycles <= 0:
            raise ValueError("max_cycles must be positive when provided.")
        return self
