"""Typed data containers for graph viewer inputs, state, and UI hitboxes."""

from __future__ import annotations

from ._graph_viewer_impl import (
    CameraState,
    GraphVisualizationData,
    GraphVisualizationError,
    GraphVisualizationOptions,
    LoadedGraphFile,
    LoadedVisualizationFile,
    NiftiVisualizationData,
    NiftiVisualizationMeshes,
    UIHitbox,
)

__all__ = [
    "CameraState",
    "GraphVisualizationData",
    "GraphVisualizationError",
    "GraphVisualizationOptions",
    "LoadedGraphFile",
    "LoadedVisualizationFile",
    "NiftiVisualizationData",
    "NiftiVisualizationMeshes",
    "UIHitbox",
]
