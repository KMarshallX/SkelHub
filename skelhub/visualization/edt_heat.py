"""EDT heatmap scene: rendering, recolouring, and picking on any PyVista plotter.

The scene works with an embedded ``pyvistaqt.QtInteractor`` or an off-screen
``pyvista.Plotter``. It owns its actors, recolours them in place (no EDT
recomputation), and maps clicks back to the original voxel or node index.

- NIfTI skeletons: one voxel block per sample, drawn by one instanced glyph
  mapper (not one mesh per voxel), each block coloured by its value band.
- GraphML: node points coloured by value plus neutral grey curved edges from
  ``centerline_voxel_points``.

Distances use the data range and the physical unit; the local EDT ratio uses
a fixed 0–1 range and no unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from skelhub.postprocessing.edt import EdtHeatResult
from skelhub.visualization._graph_viewer_impl import (
    EDGE_THICKNESS_RANGE,
    INTERACTIVE_HIGHLIGHT_SIZE_PADDING,
    INTERACTIVE_HIGHLIGHT_SIZE_SCALE,
    INTERACTIVE_PICK_RADIUS,
    INTERACTIVE_SELECTED_COLOR,
    NODE_SIZE_RANGE,
    _edge_path_polydata_arrays,
    _import_pyvista,
    _voxel_block_geometry,
)
from skelhub.visualization.heatmap import (
    BAND_COUNT_RANGE,
    COLOR_PRESETS,
    DEFAULT_BAND_COUNT,
    DEFAULT_PRESET,
    HeatLegend,
    HeatScheme,
    format_value,
    heat_colors,
)


HEAT_ARRAY = "edt_heat_rgb"
EDGE_COLOR = "#8e969c"
VOXEL_EDGE_COLOR = (31 / 255, 41 / 255, 51 / 255)
BACKGROUND_COLOR = "white"
DEFAULT_NODE_SIZE = 9.0
DEFAULT_EDGE_THICKNESS = 2.0
HIGHLIGHT_BLOCK_SCALE = 1.12


@dataclass(slots=True, frozen=True)
class RatioDetails:
    """What a local EDT ratio sample was built from (physical units, except alpha)."""

    edt: float
    local_max: float
    alpha: float
    search_radius: float
    warnings: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class HeatPick:
    """One picked voxel or node, referring back to the result by sample index.

    ``edt`` holds the displayed value: a distance, or the local EDT ratio when
    ``ratio`` is set.
    """

    index: int
    kind: str
    edt: float
    voxel_position: tuple[float, float, float]
    world_position: tuple[float, float, float]
    node_id: str | None = None
    metric_label: str = "Voxel EDT"
    ratio: RatioDetails | None = None

    def describe(self, unit_label: str) -> str:
        """Multi-line text for a details panel; ``unit_label`` is the physical unit."""
        voxel = ", ".join(format_value(value) for value in self.voxel_position)
        world = ", ".join(format_value(value) for value in self.world_position)
        lines = []
        if self.node_id is not None:
            lines.append(f"Node ID: {self.node_id}")
        if self.ratio is None:
            lines.append(f"{self.metric_label}: {format_value(self.edt)} {unit_label}")
        else:
            details = self.ratio
            lines.append(f"{self.metric_label}: {format_value(self.edt)}")
            lines.append(f"Voxel EDT: {format_value(details.edt)} {unit_label}")
            lines.append(f"Local max EDT: {format_value(details.local_max)} {unit_label}")
            lines.append(f"α: {format_value(details.alpha)} · search radius: {format_value(details.search_radius)} {unit_label}")
        lines.append(f"{'Voxel index' if self.kind == 'nifti' else 'voxel_pos'}: ({voxel})")
        lines.append(f"Position: ({world}) {unit_label}")
        if self.ratio is not None:
            lines.extend(f"Warning: {warning}" for warning in self.ratio.warnings)
        return "\n".join(lines)


def scheme_for(kind: str) -> HeatScheme:
    """NIfTI samples use discrete bands; GraphML nodes use a continuous gradient."""
    return "bands" if kind == "nifti" else "continuous"


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return float(min(max(float(value), bounds[0]), bounds[1]))


def first_voxel_hit(
    voxel_positions: np.ndarray,
    affine: np.ndarray,
    ray_origin: np.ndarray,
    ray_direction: np.ndarray,
) -> int | None:
    """Return the index of the first voxel block a physical-space ray enters.

    The ray is mapped into voxel-index space, where voxel ``c`` is the box
    ``[c - 0.5, c + 0.5]``; an affine map keeps the ray parameter, so hit order
    is the same in physical space. Only hits at or ahead of the origin count.
    """
    centres = np.asarray(voxel_positions, dtype=float).reshape((-1, 3))
    if len(centres) == 0:
        return None
    inverse = np.linalg.inv(np.asarray(affine, dtype=float))
    origin = inverse[:3, :3] @ np.asarray(ray_origin, dtype=float) + inverse[:3, 3]
    direction = inverse[:3, :3] @ np.asarray(ray_direction, dtype=float)
    if not np.isfinite(direction).all() or not np.any(direction):
        return None
    lower, upper = centres - 0.5, centres + 0.5
    with np.errstate(divide="ignore", invalid="ignore"):
        t_first = (lower - origin) / direction
        t_second = (upper - origin) / direction
    t_enter = np.minimum(t_first, t_second)
    t_exit = np.maximum(t_first, t_second)
    for axis in np.flatnonzero(direction == 0):
        inside = (lower[:, axis] <= origin[axis]) & (origin[axis] <= upper[:, axis])
        t_enter[:, axis] = np.where(inside, -np.inf, np.inf)
        t_exit[:, axis] = np.where(inside, np.inf, -np.inf)
    entry = np.max(t_enter, axis=1)
    leave = np.min(t_exit, axis=1)
    start = np.maximum(entry, 0.0)
    hit = leave >= start
    if not hit.any():
        return None
    return int(np.argmin(np.where(hit, start, np.inf)))


def project_to_display(renderer: Any, world_points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project physical points to renderer display pixels.

    Returns ``(xy[N, 2], depth[N], visible[N])`` in VTK display coordinates
    (origin bottom-left), matching interactor event positions.
    """
    points = np.asarray(world_points, dtype=float).reshape((-1, 3))
    width, height = (int(value) for value in renderer.GetSize())
    origin_x, origin_y = (int(value) for value in renderer.GetOrigin())
    if width <= 0 or height <= 0 or len(points) == 0:
        return np.empty((len(points), 2)), np.full(len(points), np.inf), np.zeros(len(points), dtype=bool)
    matrix = renderer.GetActiveCamera().GetCompositeProjectionTransformMatrix(width / height, -1.0, 1.0)
    projection = np.asarray([[matrix.GetElement(row, column) for column in range(4)] for row in range(4)])
    clip = np.column_stack((points, np.ones(len(points)))) @ projection.T
    w = clip[:, 3]
    with np.errstate(divide="ignore", invalid="ignore"):
        ndc = clip[:, :3] / w[:, None]
    visible = (w > 0) & np.all(np.isfinite(ndc), axis=1) & (np.abs(ndc[:, 2]) <= 1.0)
    xy = np.column_stack((origin_x + (ndc[:, 0] + 1.0) * 0.5 * width, origin_y + (ndc[:, 1] + 1.0) * 0.5 * height))
    return xy, ndc[:, 2], visible


def display_ray(renderer: Any, x_pos: float, y_pos: float) -> tuple[np.ndarray, np.ndarray]:
    """Physical-space ray from the near clipping plane through a display pixel."""
    def world(depth: float) -> np.ndarray:
        renderer.SetDisplayPoint(float(x_pos), float(y_pos), depth)
        renderer.DisplayToWorld()
        point = np.asarray(renderer.GetWorldPoint(), dtype=float)
        return point[:3] / point[3]

    near, far = world(0.0), world(1.0)
    return near, far - near


def _ratio_details(result: EdtHeatResult, index: int) -> RatioDetails | None:
    if not result.is_ratio:
        return None
    assert result.edt_values is not None and result.local_max_values is not None and result.search_radii is not None
    return RatioDetails(
        edt=float(result.edt_values[index]),
        local_max=float(result.local_max_values[index]),
        alpha=float(result.alpha),  # type: ignore[arg-type]
        search_radius=float(result.search_radii[index]),
        warnings=tuple(result.sample_warnings(index)),
    )


class EdtHeatScene:
    """Own and update EDT heatmap actors on one plotter."""

    def __init__(self, plotter: Any, *, pv_module: Any | None = None):
        self.plotter = plotter
        self.pv = _import_pyvista() if pv_module is None else pv_module
        self.result: EdtHeatResult | None = None
        self.legend: HeatLegend | None = None
        self.selected: HeatPick | None = None
        self.preset = DEFAULT_PRESET
        self.band_count = DEFAULT_BAND_COUNT
        self.node_size = DEFAULT_NODE_SIZE
        self.edge_thickness = DEFAULT_EDGE_THICKNESS
        self.color_updates = 0
        self._samples: Any | None = None
        self._sample_actor: Any | None = None
        self._edge_actor: Any | None = None
        self._highlight_actor: Any | None = None
        self.plotter.set_background(BACKGROUND_COLOR)

    @property
    def scheme(self) -> HeatScheme | None:
        """Colour scheme of the current result, or None when empty."""
        return None if self.result is None else scheme_for(self.result.kind)

    @property
    def sample_colors(self) -> np.ndarray | None:
        """Current per-sample RGB colours, in result sample order."""
        if self._samples is None:
            return None
        return np.asarray(self._samples.point_data[HEAT_ARRAY])

    def _render(self) -> None:
        self.plotter.render()

    def _remove(self, actor: Any | None) -> None:
        if actor is not None:
            self.plotter.remove_actor(actor, reset_camera=False, render=False)

    def clear(self, *, render: bool = True) -> None:
        """Remove every actor and forget the result."""
        for actor in (self._sample_actor, self._edge_actor, self._highlight_actor):
            self._remove(actor)
        self._samples = self._sample_actor = self._edge_actor = self._highlight_actor = None
        self.result = self.legend = self.selected = None
        if render:
            self._render()

    def show(self, result: EdtHeatResult, *, reset_camera: bool = True) -> None:
        """Replace the scene with a new result; fit the camera unless told to keep it."""
        self.clear(render=False)
        self.result = result
        colors = self._compute_colors()
        samples = self.pv.PolyData(np.asarray(result.world_positions, dtype=float))
        samples.point_data[HEAT_ARRAY] = colors
        samples.point_data.active_scalars_name = HEAT_ARRAY
        self._samples = samples
        if result.kind == "nifti":
            self._sample_actor = self._build_voxel_actor(samples, result.affine)
            self.plotter.add_actor(self._sample_actor, reset_camera=False, render=False)
        else:
            if result.edge_world_paths:
                points, lines = _edge_path_polydata_arrays(result.edge_world_paths)
                edges = self.pv.PolyData()
                edges.points = points
                edges.lines = lines
                self._edge_actor = self.plotter.add_mesh(
                    edges, color=EDGE_COLOR, line_width=self.edge_thickness,
                    render_lines_as_tubes=True, render=False, reset_camera=False, pickable=False,
                )
            self._sample_actor = self.plotter.add_mesh(
                samples, scalars=HEAT_ARRAY, rgb=True, style="points", point_size=self.node_size,
                render_points_as_spheres=True, render=False, reset_camera=False, show_scalar_bar=False,
            )
        if reset_camera:
            self.reset_view()
        else:
            self._render()

    def _build_voxel_actor(self, samples: Any, affine: np.ndarray) -> Any:
        from vtkmodules.vtkRenderingCore import vtkActor, vtkGlyph3DMapper

        mapper = vtkGlyph3DMapper()
        mapper.SetInputData(samples)
        mapper.SetSourceData(_voxel_block_geometry(affine, self.pv))
        mapper.OrientOff()
        mapper.ScalingOff()
        mapper.SetScalarModeToUsePointData()
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetEdgeVisibility(True)
        actor.GetProperty().SetEdgeColor(*VOXEL_EDGE_COLOR)
        return actor

    def _compute_colors(self) -> np.ndarray:
        assert self.result is not None
        colors, self.legend = heat_colors(
            self.result.values, scheme_for(self.result.kind), self.preset,
            band_count=self.band_count, title=self.result.value_title, value_range=self.result.value_range,
        )
        self.color_updates += 1
        return colors

    def _recolor(self) -> None:
        if self.result is None or self._samples is None:
            return
        self._samples.point_data[HEAT_ARRAY] = self._compute_colors()
        self._samples.point_data.active_scalars_name = HEAT_ARRAY
        self._samples.Modified()
        mapper = self._sample_actor.GetMapper() if self._sample_actor is not None else None
        if mapper is not None:
            mapper.Modified()
        self._render()

    def set_preset(self, preset: str) -> None:
        """Change the colour preset; camera and EDT samples are untouched."""
        if preset not in COLOR_PRESETS:
            raise ValueError(f"Unknown color preset '{preset}'.")
        self.preset = preset
        self._recolor()

    def set_band_count(self, band_count: int) -> None:
        """Change the NIfTI band count; camera and EDT samples are untouched."""
        low, high = BAND_COUNT_RANGE
        if not low <= int(band_count) <= high:
            raise ValueError(f"Color band count must be between {low} and {high}.")
        self.band_count = int(band_count)
        if self.scheme == "bands":
            self._recolor()

    def set_node_size(self, size: float) -> None:
        """Change graph node point size in pixels."""
        self.node_size = _clamp(size, NODE_SIZE_RANGE)
        if self.result is not None and self.result.kind == "graphml" and self._sample_actor is not None:
            self._sample_actor.GetProperty().SetPointSize(self.node_size)
            if self._highlight_actor is not None:
                self._highlight_actor.GetProperty().SetPointSize(self._highlight_point_size())
            self._render()

    def set_edge_thickness(self, thickness: float) -> None:
        """Change graph edge line width in pixels."""
        self.edge_thickness = _clamp(thickness, EDGE_THICKNESS_RANGE)
        if self._edge_actor is not None:
            self._edge_actor.GetProperty().SetLineWidth(self.edge_thickness)
            self._render()

    def reset_view(self) -> None:
        """Fit the camera to the current result."""
        self.plotter.reset_camera()
        self._render()

    def _highlight_point_size(self) -> float:
        return self.node_size * INTERACTIVE_HIGHLIGHT_SIZE_SCALE + INTERACTIVE_HIGHLIGHT_SIZE_PADDING

    def select(self, index: int) -> HeatPick:
        """Select a sample by index, outline it, and return its details."""
        result = self.result
        if result is None or not 0 <= int(index) < result.sample_count:
            raise IndexError(f"No sample with index {index}.")
        index = int(index)
        self._remove(self._highlight_actor)
        world = np.asarray(result.world_positions[index], dtype=float)
        if result.kind == "nifti":
            block = _voxel_block_geometry(result.affine, self.pv).scale(HIGHLIGHT_BLOCK_SCALE, inplace=False).translate(world, inplace=False)
            self._highlight_actor = self.plotter.add_mesh(
                block, color=INTERACTIVE_SELECTED_COLOR, style="wireframe", line_width=3,
                render=False, reset_camera=False, pickable=False,
            )
        else:
            self._highlight_actor = self.plotter.add_mesh(
                self.pv.PolyData(world.reshape((1, 3))), color=INTERACTIVE_SELECTED_COLOR, style="points",
                point_size=self._highlight_point_size(), render_points_as_spheres=True,
                render=False, reset_camera=False, pickable=False,
            )
        self.selected = HeatPick(
            index=index,
            kind=result.kind,
            edt=float(result.values[index]),
            voxel_position=tuple(float(value) for value in result.voxel_positions[index]),
            world_position=tuple(float(value) for value in world),
            node_id=result.node_ids[index] if result.kind == "graphml" else None,
            metric_label=result.metric_label,
            ratio=_ratio_details(result, index),
        )
        self._render()
        return self.selected

    def clear_selection(self) -> None:
        """Remove the selection outline."""
        self._remove(self._highlight_actor)
        self._highlight_actor = None
        self.selected = None
        self._render()

    def nearest_node_on_screen(self, x_pos: float, y_pos: float) -> int | None:
        """Graph node under a display pixel, preferring the front-most node that covers it."""
        if self.result is None or self.result.kind != "graphml":
            return None
        xy, depth, visible = project_to_display(self.plotter.renderer, self.result.world_positions)
        if not visible.any():
            return None
        distance = np.hypot(xy[:, 0] - x_pos, xy[:, 1] - y_pos)
        distance[~visible] = np.inf
        covering = distance <= max(self.node_size / 2.0 + 2.0, 4.0)
        if covering.any():
            return int(np.argmin(np.where(covering, depth, np.inf)))
        nearest = int(np.argmin(distance))
        return nearest if distance[nearest] <= INTERACTIVE_PICK_RADIUS else None

    def sample_at_display(self, x_pos: float, y_pos: float) -> int | None:
        """Sample index under a display pixel, or None."""
        if self.result is None or min(int(value) for value in self.plotter.renderer.GetSize()) <= 0:
            return None
        if self.result.kind == "graphml":
            return self.nearest_node_on_screen(x_pos, y_pos)
        origin, direction = display_ray(self.plotter.renderer, x_pos, y_pos)
        return first_voxel_hit(self.result.voxel_positions, self.result.affine, origin, direction)

    def pick(self, x_pos: float, y_pos: float) -> HeatPick | None:
        """Select whatever is under a display pixel; clears the selection on a miss."""
        index = self.sample_at_display(x_pos, y_pos)
        if index is None:
            if self.selected is not None:
                self.clear_selection()
            return None
        return self.select(index)

    def close(self) -> None:
        """Drop actors and references to the plotter."""
        self.clear(render=False)
