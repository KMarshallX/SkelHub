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
    input_path: str | None = None
    pred_path: str | None = None
    ref_path: str | None = None
    TP: int = 0
    FP: int = 0
    FN: int = 0
    Cp: float = 0.0
    Cr: float = 0.0
    OCC: float = 0.0
    OCC_clipped: float = 0.0
    OCC_normalized: float = 1.0
    BCC: float = 0.0
    BCC_clipped: float = 0.0
    BCC_normalized: float = 1.0
    E: float = 0.0
    E_clipped: float = 0.0
    E_normalized: float = 1.0
    P: float = 0.0
    buffer_radius: float | None = None
    buffer_radius_unit: str | None = None
    buffer_radius_mode: str | None = None
    foreground_connectivity: int = 26
    background_connectivity: int = 6
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
