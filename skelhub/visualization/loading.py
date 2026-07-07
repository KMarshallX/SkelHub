"""GraphML and NIfTI loading helpers for viewer-ready data."""

from __future__ import annotations

from ._graph_viewer_impl import (
    _bounding_boxes_overlap,
    _coerce_coordinate_array,
    _extract_edge_indices,
    _extract_node_ids,
    _extract_node_positions,
    _format_unique_preview,
    _is_binary_array,
    _is_nifti_path,
    _kind_label,
    _positions_from_xyz,
    _transform_points,
    _validate_graph_data,
    _visualization_file_kind,
    load_graph_visualization_data,
    load_nifti_visualization_data,
)

__all__ = [
    "_bounding_boxes_overlap",
    "_coerce_coordinate_array",
    "_extract_edge_indices",
    "_extract_node_ids",
    "_extract_node_positions",
    "_format_unique_preview",
    "_is_binary_array",
    "_is_nifti_path",
    "_kind_label",
    "_positions_from_xyz",
    "_transform_points",
    "_validate_graph_data",
    "_visualization_file_kind",
    "load_graph_visualization_data",
    "load_nifti_visualization_data",
]
