"""Data models for Voreen-style vessel feature extraction."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True, slots=True)
class FeatureGraphNode:
    """One graph node with a voxel-space position."""

    id: int
    voxel_pos: np.ndarray


CENTERLINE_POINTS_ATTRIBUTE = "centerline_voxel_points"
CENTERLINE_VOXELS_ATTRIBUTE = "centerline_voxels"


@dataclass(frozen=True, slots=True)
class FeatureGraphEdge:
    """One graph edge with its supplied voxel-space centerline path.

    ``path`` holds the stored geometry of the graph's edge attribute in use:
    float ``centerline_voxel_points`` oriented from node 1 to node 2 (both
    endpoints included), or integer ``centerline_voxels`` as stored.
    """

    id: int
    node1_id: int
    node2_id: int
    path: np.ndarray


@dataclass(frozen=True, slots=True)
class FeatureGraph:
    """Graph geometry read from a supported GraphML export."""

    source: str
    nodes: tuple[FeatureGraphNode, ...]
    edges: tuple[FeatureGraphEdge, ...]
    geometry_attribute: str = CENTERLINE_VOXELS_ATTRIBUTE

    @property
    def uses_centerline_points(self) -> bool:
        """Whether edge paths are float ``centerline_voxel_points``."""
        return self.geometry_attribute == CENTERLINE_POINTS_ATTRIBUTE


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
    """Feature rows plus measurement-space metadata.

    ``geometry_attribute`` names the GraphML edge attribute used as branch
    geometry. ``sampling_step`` is the maximum spacing (voxels) of radius
    samples along ``centerline_voxel_points``; ``None`` for ``centerline_voxels``.
    """

    edges: tuple[FeatureEdgeRecord, ...]
    nodes: tuple[FeatureNodeRecord, ...]
    physical_unit: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    geometry_attribute: str = CENTERLINE_VOXELS_ATTRIBUTE
    sampling_step: float | None = None
