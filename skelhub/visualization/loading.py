"""GraphML and NIfTI loading helpers for viewer-ready data."""

from __future__ import annotations

from ._graph_viewer_impl import (
    _bounding_boxes_overlap,
    _coerce_coordinate_array,
    _extract_edge_indices,
    _extract_node_ids,
    _extract_node_positions,
    _infer_voxel_to_world_affine,
    _load_edge_world_paths,
    _load_optional_edge_geometries,
    _parse_graphml_path,
    _parse_graphml_point,
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
    "_infer_voxel_to_world_affine",
    "_load_edge_world_paths",
    "_load_optional_edge_geometries",
    "_parse_graphml_path",
    "_parse_graphml_point",
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
