"""Framework-level data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class VolumeData:
    """Standardized in-memory NIfTI volume."""

    data: np.ndarray
    affine: np.ndarray
    header: Any
    path: str | None = None
    spacing: tuple[float, float, float] | None = None


@dataclass(slots=True)
class GraphResult:
    """Placeholder graph container for future postprocessing stages."""

    nodes: list[tuple[int, int, int]] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkeletonResult:
    """Standardized skeletonization result returned by all backends."""

    algorithm_name: str
    skeleton: np.ndarray
    input_metadata: dict[str, Any] = field(default_factory=dict)
    runtime_stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    backend_metadata: dict[str, Any] = field(default_factory=dict)
    graph: GraphResult | None = None


@dataclass(slots=True)
class EvaluationResult:
    """Standardized evaluation result."""

    message: str
    input_path: str
    metadata: dict[str, Any] = field(default_factory=dict)
