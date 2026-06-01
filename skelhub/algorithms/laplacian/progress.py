"""Verbose progress reporting for the Laplacian backend."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable


def _format_duration(seconds: float, *, round_up: bool = False) -> str:
    """Format a non-negative duration as HH:MM:SS."""
    rounded = math.ceil(seconds) if round_up else int(seconds)
    rounded = max(rounded, 0)
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


@dataclass
class LaplacianProgress:
    """Emit connected-component progress and estimated time remaining."""

    log: Callable[[str], None]
    total_components: int | None = None
    stages: tuple[str, ...] = ()
    width: int = 24
    started: float = field(default_factory=time.perf_counter)
    completed: int = 0
    current_component: int | None = None
    estimated_total_seconds: float | None = None

    def found(self, *, foreground_voxels: int) -> None:
        """Report the number of foreground components discovered."""
        total = self._total()
        self.log(
            f"laplacian components found: count={total}, "
            f"foreground_voxels={int(foreground_voxels)}"
        )

    def start_component(
        self,
        *,
        index: int,
        component_label: int,
        voxel_count: int,
        bbox: tuple[tuple[int, int], tuple[int, int], tuple[int, int]],
    ) -> None:
        """Mark one component as running."""
        self.current_component = int(index)
        self._emit(
            "running",
            (
                f"label={int(component_label)}, voxels={int(voxel_count)}, "
                f"bbox={bbox}"
            ),
            component=index,
        )

    def finish_component(
        self,
        *,
        index: int,
        component_label: int,
        output_voxels: int,
        elapsed_seconds: float,
        cleaned_nodes: int,
        cleaned_edges: int,
    ) -> None:
        """Complete one component."""
        self.completed = min(int(index), self._total())
        self.current_component = None
        elapsed = time.perf_counter() - self.started
        total = self._total()
        self.estimated_total_seconds = max(elapsed, (elapsed / self.completed) * total)
        self._emit(
            "complete",
            (
                f"label={int(component_label)}, output_voxels={int(output_voxels)}, "
                f"cleaned_nodes={int(cleaned_nodes)}, cleaned_edges={int(cleaned_edges)}, "
                f"component_time={elapsed_seconds:.2f}s"
            ),
            component=index,
        )

    def finish_all(self, *, output_voxels: int, runtime_seconds: float) -> None:
        """Report final output summary."""
        self.log(
            f"laplacian components complete: count={self._total()}, "
            f"output_voxels={int(output_voxels)}, runtime={runtime_seconds:.2f}s"
        )

    def start(self, stage: str) -> None:
        """Compatibility no-op for older stage progress callers."""
        return None

    def detail(self, detail: str) -> None:
        """Publish optional backend detail without stage progress."""
        self.log(f"laplacian detail: {detail}")

    def finish(self, detail: str | None = None) -> None:
        """Compatibility no-op for older stage progress callers."""
        if detail:
            self.log(f"laplacian detail: {detail}")

    def _total(self) -> int:
        return max(int(self.total_components or len(self.stages) or 1), 1)

    def _emit(
        self,
        status: str,
        detail: str | None = None,
        *,
        component: int | None = None,
    ) -> None:
        elapsed = time.perf_counter() - self.started
        total = self._total()
        completed = min(self.completed, total)
        filled = int(self.width * completed / total)
        bar = "=" * filled
        if status == "running" and filled < self.width:
            bar += ">"
        bar = bar.ljust(self.width, ".")

        if completed == 0 or self.estimated_total_seconds is None:
            remaining = "estimating"
        else:
            seconds_remaining = max(self.estimated_total_seconds - elapsed, 0.0)
            remaining = _format_duration(seconds_remaining, round_up=True)

        current = component or self.current_component or completed
        message = (
            f"laplacian [{bar}] {completed}/{total} ({completed / total:3.0%}) "
            f"component={current}/{total} | {status} | "
            f"elapsed={_format_duration(elapsed)} | remaining~{remaining}"
        )
        if detail:
            message += f" | {detail}"
        self.log(message)
