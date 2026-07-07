"""PyVista scene construction and active visualization rendering."""

from __future__ import annotations

from ._graph_viewer_impl import (
    _add_graph_scene,
    _add_overlay_graph,
    _build_instanced_nifti_actor,
    _edge_polyline_array,
    _import_pyvista,
    _nifti_display_positions,
    _nifti_voxel_geometry,
    _remove_graph_actors,
    _render_overlay_layers,
    _set_actor_opacity,
    _update_graph_appearance,
    _validate_options,
    build_graph_plotter,
    build_nifti_meshes,
    refresh_active_graph,
    render_active_graph,
)

__all__ = [
    "_add_graph_scene",
    "_add_overlay_graph",
    "_build_instanced_nifti_actor",
    "_edge_polyline_array",
    "_import_pyvista",
    "_nifti_display_positions",
    "_nifti_voxel_geometry",
    "_remove_graph_actors",
    "_render_overlay_layers",
    "_set_actor_opacity",
    "_update_graph_appearance",
    "_validate_options",
    "build_graph_plotter",
    "build_nifti_meshes",
    "refresh_active_graph",
    "render_active_graph",
]
