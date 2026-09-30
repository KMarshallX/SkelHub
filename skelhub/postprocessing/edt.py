"""Foreground boundary distance sampled at skeleton locations.

GUI-independent. Given a binary foreground NIfTI and either a binary skeleton
NIfTI or a GraphML graph, this module validates that both describe the same
voxel grid and samples one of two physical distances:

- ``voxel_edt`` (default): the Euclidean distance transform from foreground
  voxel centres to background voxel centres, read at every occupied skeleton
  voxel, or trilinearly interpolated at each GraphML node ``voxel_pos``.
- ``surface`` (GraphML only): the shortest distance from each node to the
  unsmoothed 0.5 isosurface of the foreground; see
  ``skelhub.postprocessing.surface_distance``.

With ``metric="local_edt_ratio"`` the Voxel EDT samples are turned into the
dimensionless local EDT ratio from ``skelhub.evaluation.centeredness``,
searching the sample's 26-connected foreground component.

Sampled geometry is placed in physical space with the *foreground* affine.
No algorithm backend is involved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

import numpy as np
from scipy import ndimage

from skelhub.evaluation.centeredness import (
    CONNECTIVITY,
    DEFAULT_ALPHA,
    CenterednessError,
    component_ids_at_points,
    component_ids_at_voxels,
    label_foreground_components,
    local_edt_ratio,
    validate_alpha,
)
from skelhub.io.graphml_reader import GraphVoxelGeometry, read_graph_voxel_geometry
from skelhub.io.nifti_reader import BinaryMaskVolume, read_binary_mask
from skelhub.postprocessing.checker import FOREGROUND_CELL_TOLERANCE, points_in_foreground_cells
from skelhub.postprocessing.surface_distance import (
    SURFACE_PARAMETERS,
    SurfaceCache,
    SurfaceDistanceError,
    build_foreground_surface,
    file_identity,
    surface_distances,
)


Progress = Callable[[int | None, str], None]
SkeletonKind = Literal["nifti", "graphml"]
DistanceMethod = Literal["voxel_edt", "surface"]
DISTANCE_METHODS: tuple[DistanceMethod, ...] = ("voxel_edt", "surface")
DISTANCE_METHOD_LABELS: dict[str, str] = {"voxel_edt": "Voxel EDT", "surface": "Surface distance"}
Metric = Literal["distance", "local_edt_ratio"]
METRICS: tuple[Metric, ...] = ("distance", "local_edt_ratio")
METRIC_LABELS: dict[str, str] = {"distance": "Distance", "local_edt_ratio": "Local EDT ratio"}
RATIO_VALUE_RANGE = (0.0, 1.0)

# Placement tolerance, as a fraction of the smallest voxel spacing.
ALIGNMENT_TOLERANCE_VOXELS = 1e-3
# Largest accepted |cos(angle)| between affine voxel axes before the grid counts as sheared.
SHEAR_TOLERANCE = 1e-5
SPATIAL_UNIT_LABELS = {"mm": "mm", "meter": "m", "micron": "µm"}


class EdtInputError(ValueError):
    """Raised when EDT inputs are malformed, empty, or spatially incompatible."""


@dataclass(slots=True)
class EdtHeatResult:
    """Per-sample values at skeleton voxels or graph nodes, placed in physical space.

    ``metric`` says what ``values`` hold:

    - ``distance`` (default): the physical distance named by ``distance_method``
      (``voxel_edt`` or ``surface``).
    - ``local_edt_ratio``: the dimensionless local EDT ratio. The Voxel EDT at
      each sample is then in ``edt_values``, the local maximum EDT in
      ``local_max_values``, and the search radius in ``search_radii`` (all
      physical); ``alpha`` and ``connectivity`` record the settings. These
      fields are None for distance results.

    ``voxel_positions`` are indices in the foreground grid; ``world_positions``
    are the same points through the foreground affine. For GraphML,
    ``edge_world_paths`` holds each edge's ``centerline_voxel_points`` in
    physical space for rendering only; edges carry no samples.
    """

    kind: SkeletonKind
    values: np.ndarray
    voxel_positions: np.ndarray
    world_positions: np.ndarray
    affine: np.ndarray
    spacing: tuple[float, float, float]
    spatial_unit: str | None
    shape: tuple[int, int, int]
    foreground_path: str
    skeleton_path: str
    node_ids: tuple[str, ...] = ()
    edge_world_paths: tuple[np.ndarray, ...] = ()
    warnings: list[str] = field(default_factory=list)
    distance_method: DistanceMethod = "voxel_edt"
    metric: Metric = "distance"
    alpha: float | None = None
    connectivity: int | None = None
    edt_values: np.ndarray | None = None
    local_max_values: np.ndarray | None = None
    search_radii: np.ndarray | None = None
    component_ids: np.ndarray | None = None
    neighbour_counts: np.ndarray | None = None
    extends_beyond_image: np.ndarray | None = None

    @property
    def sample_count(self) -> int:
        """Number of sampled voxels or nodes."""
        return int(self.values.shape[0])

    @property
    def is_ratio(self) -> bool:
        """True when ``values`` hold the dimensionless local EDT ratio."""
        return self.metric == "local_edt_ratio"

    @property
    def metric_label(self) -> str:
        """Display name of what ``values`` hold."""
        return METRIC_LABELS["local_edt_ratio"] if self.is_ratio else DISTANCE_METHOD_LABELS[self.distance_method]

    @property
    def settings_label(self) -> str:
        """Metric name with its settings, e.g. "Local EDT ratio (α = 1.5)"."""
        return f"{self.metric_label} (α = {self.alpha:g})" if self.is_ratio else self.metric_label

    @property
    def unit_label(self) -> str:
        """Physical unit for distances and positions; never guesses a unit the header does not state."""
        return self.spatial_unit if self.spatial_unit else "unit unspecified"

    @property
    def value_unit_label(self) -> str | None:
        """Unit of ``values``: the physical unit for distances, None for the dimensionless ratio."""
        return None if self.is_ratio else self.unit_label

    @property
    def value_title(self) -> str:
        """Legend title: the metric, with a unit only when ``values`` have one."""
        unit = self.value_unit_label
        return self.metric_label if unit is None else f"{self.metric_label} ({unit})"

    @property
    def value_range(self) -> tuple[float, float] | None:
        """Fixed colour range for ``values`` (0–1 for the ratio), or None to use the data range."""
        return RATIO_VALUE_RANGE if self.is_ratio else None

    def sample_warnings(self, index: int) -> list[str]:
        """Warnings that apply to one sample."""
        warnings = []
        if self.extends_beyond_image is not None and bool(self.extends_beyond_image[index]):
            warnings.append("Search ball reaches beyond the image; only observed voxels were searched.")
        if self.neighbour_counts is not None and int(self.neighbour_counts[index]) == 0:
            warnings.append("Limited neighbourhood support: no other same-component voxel in the search ball.")
        return warnings


def spatial_unit_label(header_unit: str) -> str | None:
    """Map a nibabel spatial-unit name to a short label, or None when unknown."""
    return SPATIAL_UNIT_LABELS.get(str(header_unit))


def voxel_spacing_from_affine(affine: np.ndarray) -> tuple[float, float, float]:
    """Return the physical voxel spacing along each array axis.

    Rotated grids are accepted because their axes stay orthogonal. Sheared grids
    are rejected: a per-axis spacing EDT would give wrong distances on them.
    """
    linear = np.asarray(affine, dtype=float)[:3, :3]
    if not np.isfinite(linear).all():
        raise EdtInputError("Foreground affine contains non-finite values.")
    spacing = np.linalg.norm(linear, axis=0)
    if np.any(spacing <= 0) or abs(np.linalg.det(linear)) <= 1e-12 * float(np.prod(spacing)):
        raise EdtInputError("Foreground affine is singular; voxel spacing is undefined.")
    unit_axes = linear / spacing
    gram = unit_axes.T @ unit_axes
    off_diagonal = np.abs(gram[~np.eye(3, dtype=bool)])
    if float(off_diagonal.max()) > SHEAR_TOLERANCE:
        raise EdtInputError(
            "Foreground voxel grid is sheared (voxel axes are not orthogonal; "
            f"largest |cos angle| = {float(off_diagonal.max()):.3g}). "
            "Physical EDT with per-axis spacing would be wrong, so this grid is not supported."
        )
    return tuple(float(value) for value in spacing)  # type: ignore[return-value]


def _foreground_crop(mask: np.ndarray) -> tuple[slice, ...]:
    """Bounding box of the foreground, padded by one voxel where the volume allows.

    The one-voxel pad is background, so every foreground voxel's nearest
    background voxel lies inside the crop: any background voxel outside it is
    farther away than its projection onto the pad layer. The EDT on the crop
    therefore equals the full-volume EDT.
    """
    occupied = np.nonzero(mask.any(axis=(1, 2)))[0], np.nonzero(mask.any(axis=(0, 2)))[0], np.nonzero(mask.any(axis=(0, 1)))[0]
    return tuple(
        slice(max(int(axis[0]) - 1, 0), min(int(axis[-1]) + 2, size))
        for axis, size in zip(occupied, mask.shape)
    )


def foreground_edt(mask: np.ndarray, spacing: tuple[float, float, float]) -> tuple[np.ndarray, tuple[int, int, int]]:
    """Physical EDT of a binary foreground: distance from each voxel centre to the nearest background centre.

    Returns the EDT over the padded foreground bounding box and that box's
    origin in the full volume. Background voxels are 0; foreground voxels next
    to background equal the spacing along that axis. The volume border is not
    treated as background.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 3:
        raise EdtInputError(f"Foreground must be 3D; got {mask.ndim}D.")
    if not mask.any():
        raise EdtInputError("Foreground is empty (no voxels equal 1); the EDT is undefined.")
    if mask.all():
        raise EdtInputError(
            "Foreground fills the whole volume (no background voxels). "
            "The distance to background is undefined, and the volume border is not treated as background."
        )
    crop = _foreground_crop(mask)
    distances = ndimage.distance_transform_edt(mask[crop], sampling=spacing)
    return distances, tuple(int(part.start) for part in crop)  # type: ignore[return-value]


def sample_edt_at_voxels(edt: np.ndarray, voxel_indices: np.ndarray, origin: tuple[int, int, int] = (0, 0, 0)) -> np.ndarray:
    """Read EDT values at integer voxel indices given in full-volume coordinates."""
    local = np.asarray(voxel_indices, dtype=np.int64) - np.asarray(origin, dtype=np.int64)
    return np.asarray(edt[tuple(local.T)], dtype=float)


def sample_edt_at_points(edt: np.ndarray, points: np.ndarray, origin: tuple[int, int, int] = (0, 0, 0)) -> np.ndarray:
    """Trilinearly interpolate EDT values at fractional voxel-space points.

    Integer points return the exact voxel value. Points within half a voxel of
    the array edge use the nearest edge value beyond the last voxel centre.
    """
    local = np.asarray(points, dtype=float) - np.asarray(origin, dtype=float)
    if len(local) == 0:
        return np.empty(0, dtype=float)
    return ndimage.map_coordinates(edt, local.T, order=1, mode="nearest", prefilter=False)


def apply_affine(affine: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Transform voxel-space points to physical space."""
    points = np.asarray(points, dtype=float).reshape((-1, 3))
    return points @ np.asarray(affine, dtype=float)[:3, :3].T + np.asarray(affine, dtype=float)[:3, 3]


def _alignment_tolerance(spacing: tuple[float, float, float]) -> float:
    return ALIGNMENT_TOLERANCE_VOXELS * min(spacing)


def _volume_corners(shape: tuple[int, int, int]) -> np.ndarray:
    return np.asarray([[i, j, k] for i in (0, shape[0] - 1) for j in (0, shape[1] - 1) for k in (0, shape[2] - 1)], dtype=float)


def _check_nifti_pair(foreground: BinaryMaskVolume, skeleton: BinaryMaskVolume, spacing: tuple[float, float, float]) -> None:
    if foreground.shape != skeleton.shape:
        raise EdtInputError(
            f"Foreground and skeleton shapes differ: {foreground.shape} != {skeleton.shape}. "
            "Inputs are not resampled automatically."
        )
    corners = _volume_corners(foreground.shape)
    offset = float(np.max(np.linalg.norm(apply_affine(foreground.affine, corners) - apply_affine(skeleton.affine, corners), axis=1)))
    if offset > _alignment_tolerance(spacing):
        raise EdtInputError(
            "Foreground and skeleton affines differ: the same voxel maps to physical positions "
            f"up to {offset:.4g} apart. Inputs are not registered or resampled automatically."
        )
    if not skeleton.mask.any():
        raise EdtInputError("Skeleton NIfTI is empty (no voxels equal 1); there is nothing to sample.")
    if np.any(skeleton.mask & ~foreground.mask):
        raise EdtInputError(
            "Some skeleton voxels lie outside the foreground, so the skeleton and foreground "
            "do not match. EDT Heat requires every skeleton voxel inside the foreground."
        )


def _check_graph_against_foreground(
    graph: GraphVoxelGeometry,
    foreground: BinaryMaskVolume,
    spacing: tuple[float, float, float],
) -> None:
    inside = points_in_foreground_cells(graph.voxel_positions, foreground.mask)
    if not inside.all():
        first = int(np.flatnonzero(~inside)[0])
        point = ", ".join(f"{value:g}" for value in graph.voxel_positions[first])
        raise EdtInputError(
            f"Graph node '{graph.node_ids[first]}' voxel_pos ({point}) lies outside the foreground "
            "(checker convention: every node must fall in an occupied voxel cell). "
            "The graph and foreground do not match."
        )
    limit = np.asarray(foreground.shape, dtype=float) - 0.5 + FOREGROUND_CELL_TOLERANCE
    for index, path in enumerate(graph.edge_voxel_paths):
        if np.any(path < -0.5 - FOREGROUND_CELL_TOLERANCE) or np.any(path > limit):
            raise EdtInputError(
                f"Edge {index} centerline_voxel_points leave the foreground volume extent {foreground.shape}. "
                "The graph and foreground do not match."
            )
    tolerance = _alignment_tolerance(spacing)
    if graph.world_positions is not None:
        offset = float(np.max(np.linalg.norm(apply_affine(foreground.affine, graph.voxel_positions) - graph.world_positions, axis=1)))
        if offset > tolerance:
            raise EdtInputError(
                "Graph node X/Y/Z coordinates disagree with the foreground affine applied to voxel_pos "
                f"(largest offset {offset:.4g}). The graph was likely built on a different image grid."
            )
    if graph.edge_world_paths is not None:
        for index, (voxel_path, world_path) in enumerate(zip(graph.edge_voxel_paths, graph.edge_world_paths)):
            offset = float(np.max(np.linalg.norm(apply_affine(foreground.affine, voxel_path) - world_path, axis=1)))
            if offset > tolerance:
                raise EdtInputError(
                    f"Edge {index} centerline_world_points disagree with the foreground affine applied to "
                    f"centerline_voxel_points (largest offset {offset:.4g})."
                )


def _is_nifti(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".nii") or name.endswith(".nii.gz")


def skeleton_kind(path: str | Path) -> SkeletonKind:
    """Classify a skeleton input by extension."""
    candidate = Path(path)
    if candidate.suffix.lower() == ".graphml":
        return "graphml"
    if _is_nifti(candidate):
        return "nifti"
    raise EdtInputError(f"Unsupported skeleton input: {candidate}. Expected .graphml, .nii, or .nii.gz.")


def compute_edt_heat(
    foreground_path: str | Path,
    skeleton_path: str | Path,
    progress: Progress | None = None,
    *,
    method: DistanceMethod = "voxel_edt",
    surface_cache: SurfaceCache | None = None,
    metric: Metric = "distance",
    alpha: float | None = None,
) -> EdtHeatResult:
    """Validate inputs and sample the chosen boundary distance or local EDT ratio at the skeleton.

    ``method="surface"`` is available for GraphML skeletons only. A
    ``surface_cache`` lets repeated calls reuse the reconstructed surface for
    an unchanged foreground file.

    ``metric="local_edt_ratio"`` needs ``method="voxel_edt"``. ``alpha`` (the
    search-radius multiplier, 1.0–3.0, default 1.5) applies to that metric
    only; passing it with ``metric="distance"`` is an error, so distance
    results never depend on it.

    Raises ``EdtInputError`` (a ``ValueError``) for malformed, empty, or
    misaligned inputs, for invalid settings, and for nodes the surface method
    cannot place. A passing spatial check shows the inputs share a grid; it
    cannot prove they came from the same source data.
    """
    def update(percent: int | None, message: str) -> None:
        if progress:
            progress(percent, message)

    if method not in DISTANCE_METHODS:
        raise EdtInputError(f"Unknown distance method '{method}'. Choose one of: {', '.join(DISTANCE_METHODS)}.")
    if metric not in METRICS:
        raise EdtInputError(f"Unknown metric '{metric}'. Choose one of: {', '.join(METRICS)}.")
    ratio = metric == "local_edt_ratio"
    if ratio:
        if method != "voxel_edt":
            raise EdtInputError(
                "Local EDT ratio uses Voxel EDT; a centeredness measure based on Surface distance is not available yet."
            )
        try:
            alpha = validate_alpha(DEFAULT_ALPHA if alpha is None else alpha)
        except CenterednessError as exc:
            raise EdtInputError(str(exc)) from exc
    elif alpha is not None:
        raise EdtInputError("The radius multiplier alpha applies only to metric='local_edt_ratio'.")
    kind = skeleton_kind(skeleton_path)
    if method == "surface" and kind != "graphml":
        raise EdtInputError("Surface distance currently supports GraphML skeletons only; use Voxel EDT for NIfTI skeletons.")
    update(5, f"Loading foreground: {Path(foreground_path).name}")
    try:
        foreground = read_binary_mask(foreground_path, label="Foreground")
    except EdtInputError:
        raise
    except ValueError as exc:
        raise EdtInputError(str(exc)) from exc
    spacing = voxel_spacing_from_affine(foreground.affine)
    unit = spatial_unit_label(foreground.spatial_unit)
    warnings: list[str] = []
    if unit is None:
        warnings.append(
            f"Foreground header spatial unit is '{foreground.spatial_unit}'; distances are in affine units without a unit label."
        )
    if not foreground.mask.any():
        raise EdtInputError("Foreground is empty (no voxels equal 1); the EDT is undefined.")
    if foreground.mask.all():
        raise EdtInputError(
            "Foreground fills the whole volume (no background voxels). "
            "The distance to background is undefined, and the volume border is not treated as background."
        )

    update(20, f"Loading skeleton: {Path(skeleton_path).name}")
    try:
        if kind == "nifti":
            skeleton = read_binary_mask(skeleton_path, label="Skeleton")
            update(30, "Checking skeleton shape, affine, and foreground containment")
            _check_nifti_pair(foreground, skeleton, spacing)
            voxel_positions = np.argwhere(skeleton.mask)
            graph = None
        else:
            graph = read_graph_voxel_geometry(skeleton_path)
            update(30, f"Checking {len(graph.node_ids)} graph nodes and {len(graph.edge_voxel_paths)} edge paths against the foreground")
            _check_graph_against_foreground(graph, foreground, spacing)
            voxel_positions = graph.voxel_positions
    except EdtInputError:
        raise
    except ValueError as exc:
        raise EdtInputError(str(exc)) from exc

    ratio_fields: dict[str, object] = {}
    if method == "surface":
        assert graph is not None
        values = _surface_values(foreground, graph, spacing, foreground_path, surface_cache, warnings, update)
    else:
        update(None, f"Computing physical EDT on {foreground.shape} foreground (spacing {', '.join(f'{s:g}' for s in spacing)})")
        edt, origin = foreground_edt(foreground.mask, spacing)
        update(50 if ratio else 85, "Sampling EDT at skeleton " + ("voxels" if kind == "nifti" else "nodes"))
        if kind == "nifti":
            values = sample_edt_at_voxels(edt, voxel_positions, origin)
        else:
            values = sample_edt_at_points(edt, voxel_positions, origin)
        if ratio:
            assert alpha is not None
            ratio_fields = _ratio_fields(foreground, graph, edt, origin, voxel_positions, values, spacing, alpha, warnings, update)
            values = ratio_fields.pop("ratios")
        del edt

    edge_world_paths: tuple[np.ndarray, ...] = ()
    node_ids: tuple[str, ...] = ()
    if graph is not None:
        node_ids = graph.node_ids
        edge_world_paths = tuple(apply_affine(foreground.affine, path) for path in graph.edge_voxel_paths)
    update(95, f"Sampled {len(values)} {'voxels' if kind == 'nifti' else 'nodes'}")
    return EdtHeatResult(
        kind=kind,
        values=np.asarray(values, dtype=float),
        voxel_positions=np.asarray(voxel_positions, dtype=float if kind == "graphml" else np.int64),
        world_positions=apply_affine(foreground.affine, voxel_positions),
        affine=foreground.affine.copy(),
        spacing=spacing,
        spatial_unit=unit,
        shape=foreground.shape,
        foreground_path=str(foreground_path),
        skeleton_path=str(skeleton_path),
        node_ids=node_ids,
        edge_world_paths=edge_world_paths,
        warnings=warnings,
        distance_method=method,
        metric=metric,
        **ratio_fields,  # type: ignore[arg-type]
    )


def _ratio_fields(
    foreground: BinaryMaskVolume,
    graph: GraphVoxelGeometry | None,
    edt: np.ndarray,
    origin: tuple[int, int, int],
    voxel_positions: np.ndarray,
    sample_edt: np.ndarray,
    spacing: tuple[float, float, float],
    alpha: float,
    warnings: list[str],
    update: Progress,
) -> dict[str, object]:
    """Local EDT ratio on the EDT crop; returns the ratio-specific result fields plus ``ratios``.

    The crop holds every foreground voxel (bounding box plus one background
    voxel), so labelling it gives the same components as the full volume and
    clipping searches to it drops only background. Image-border warnings use
    the full image shape, not the crop.
    """
    crop = tuple(slice(start, start + size) for start, size in zip(origin, edt.shape))
    update(None, f"Labelling {CONNECTIVITY}-connected foreground components")
    labels, component_count = label_foreground_components(foreground.mask[crop])
    try:
        if graph is None:
            component_ids = component_ids_at_voxels(labels, voxel_positions, origin)
        else:
            component_ids = component_ids_at_points(labels, voxel_positions, origin, graph.node_ids)
        update(55, f"Searching {len(sample_edt)} neighbourhoods across {component_count} components (α = {alpha:g})")
        result = local_edt_ratio(
            edt, labels, voxel_positions, sample_edt, component_ids, spacing, alpha,
            origin=origin, image_shape=foreground.shape,
            progress=lambda percent, message: update(55 + (percent or 0) * 35 // 100, message),
            sample_names=graph.node_ids if graph is not None else None,
        )
    except CenterednessError as exc:
        raise EdtInputError(str(exc)) from exc
    warnings.extend(result.warnings)
    return {
        "ratios": result.ratios,
        "alpha": result.alpha,
        "connectivity": result.connectivity,
        "edt_values": result.sample_edt,
        "local_max_values": result.local_max_edt,
        "search_radii": result.search_radii,
        "component_ids": result.component_ids,
        "neighbour_counts": result.neighbour_counts,
        "extends_beyond_image": result.extends_beyond_image,
    }


def _surface_values(
    foreground: BinaryMaskVolume,
    graph: GraphVoxelGeometry,
    spacing: tuple[float, float, float],
    foreground_path: str | Path,
    surface_cache: SurfaceCache | None,
    warnings: list[str],
    update: Progress,
) -> np.ndarray:
    def build():
        return build_foreground_surface(foreground.mask, foreground.affine, spacing, update)

    try:
        if surface_cache is None:
            surface = build()
        else:
            key = (file_identity(foreground_path), SURFACE_PARAMETERS)
            surface, reused = surface_cache.get(key, build)
            if reused:
                update(None, "Reusing the reconstructed surface for the unchanged foreground")
        if surface.open_border_faces:
            warnings.append(
                "Foreground reaches the image border at " + ", ".join(surface.open_border_faces)
                + ". The surface is left open there, so distances are measured to the observed surface only; "
                "an unobserved boundary beyond the image could be closer."
            )
        values = surface_distances(surface, graph.voxel_positions, graph.node_ids, update)
    except SurfaceDistanceError as exc:
        raise EdtInputError(str(exc)) from exc
    update(90, f"Surface distance measured for {len(values)} nodes ({surface.triangle_count} triangles)")
    return values
