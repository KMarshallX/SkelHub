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
    """Emit stage-level progress and estimated time remaining."""

    log: Callable[[str], None]
    stages: tuple[str, ...]
    width: int = 24
    started: float = field(default_factory=time.perf_counter)
    completed: int = 0
    current_stage: str | None = None
    estimated_total_seconds: float | None = None

    def start(self, stage: str) -> None:
        """Mark a pipeline stage as running."""
        self.current_stage = stage
        self._emit("running")

    def detail(self, detail: str) -> None:
        """Publish detail for the running stage without advancing the bar."""
        if self.current_stage is not None:
            self._emit("running", detail)

    def finish(self, detail: str | None = None) -> None:
        """Complete the current pipeline stage."""
        if self.current_stage is None:
            return
        stage = self.current_stage
        self.completed = min(self.completed + 1, len(self.stages))
        self.current_stage = None
        elapsed = time.perf_counter() - self.started
        total = max(len(self.stages), 1)
        self.estimated_total_seconds = max(elapsed, (elapsed / self.completed) * total)
        self._emit("complete", detail, stage=stage)

    def _emit(self, status: str, detail: str | None = None, *, stage: str | None = None) -> None:
        elapsed = time.perf_counter() - self.started
        total = max(len(self.stages), 1)
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

        current = stage or self.current_stage or "complete"
        message = (
            f"laplacian [{bar}] {completed}/{total} ({completed / total:3.0%}) "
            f"stage={current} | {status} | elapsed={_format_duration(elapsed)} | remaining~{remaining}"
        )
        if detail:
            message += f" | {detail}"
        self.log(message)
