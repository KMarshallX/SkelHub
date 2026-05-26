"""Data models for Voreen-style vessel feature extraction."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True, slots=True)
class FeatureGraphNode:
    """One graph node with a voxel-space position."""

    id: int
    voxel_pos: np.ndarray


@dataclass(frozen=True, slots=True)
class FeatureGraphEdge:
    """One graph edge with its supplied voxel-space centerline path."""

    id: int
    node1_id: int
    node2_id: int
    centerline_voxels: np.ndarray


@dataclass(frozen=True, slots=True)
class FeatureGraph:
    """Graph geometry read from a supported GraphML export."""

    source: str
    nodes: tuple[FeatureGraphNode, ...]
    edges: tuple[FeatureGraphEdge, ...]


@dataclass(frozen=True, slots=True)
class FeatureEdgeRecord:
    """Output values for one vessel branch."""

    id: int
    node1_id: int
    node2_id: int
    length: float
    minRadius: float
    avgRadius: float
    maxRadius: float
    curveness: float
    node1_degree: int
    node2_degree: int
    length_image: float
    minRadius_image: float
    avgRadius_image: float
    maxRadius_image: float
    curveness_image: float


@dataclass(frozen=True, slots=True)
class FeatureNodeRecord:
    """Output values for one graph node."""

    id: int
    position_x: float
    position_y: float
    position_z: float
    degree: int


@dataclass(frozen=True, slots=True)
class FeatureExtractionResult:
    """Feature rows plus measurement-space metadata."""

    edges: tuple[FeatureEdgeRecord, ...]
    nodes: tuple[FeatureNodeRecord, ...]
    physical_unit: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
