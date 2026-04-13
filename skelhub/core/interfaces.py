"""Framework interfaces."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from .models import SkeletonResult, VolumeData


class SkeletonBackend(Protocol):
    """Contract that all algorithm backends must satisfy."""

    name: str

    def build_config(self, args: Any) -> Any:
        """Build a validated backend config object from CLI or API args."""

    def run(
        self,
        volume: VolumeData,
        config: Any,
        log: Callable[[str], None] | None = None,
    ) -> SkeletonResult:
        """Execute the backend and return a standardized result."""
