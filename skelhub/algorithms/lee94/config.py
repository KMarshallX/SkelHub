"""Lee94 backend configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Lee94Config:
    """Validated runtime parameters for the Lee94 backend."""

    binarize_threshold: float = 0.5

    def validate(self) -> "Lee94Config":
        """Validate config values and return self for chaining."""
        if not (0.0 <= self.binarize_threshold <= 1.0):
            raise ValueError("binarize_threshold must be between 0.0 and 1.0.")
        return self
