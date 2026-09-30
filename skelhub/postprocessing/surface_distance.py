"""Distance from graph nodes to the foreground's reconstructed boundary surface.

The surface is the unsmoothed 0.5 isosurface of the binary foreground, built
with full-resolution marching cubes (scikit-image, Lewiner variant) and placed
in physical space with the complete NIfTI affine. Two meshes are kept:

- the *distance mesh*: marching cubes on the image as observed. Where the
  foreground reaches the image border the surface is left open; nothing is
  capped, padded, or filled, so every triangle lies between observed voxels.
- the *closure mesh*: the same extraction on a copy padded with one layer of
  background. It is closed and is used only to decide whether a node is inside.
  Inside the voxel-centre hull ``[0, n - 1]`` per axis it coincides with the
  distance mesh; its extra triangles lie outside that hull and never enter a
  reported distance.

Nodes beyond the voxel-centre hull (the outer half-voxel strip) are rejected:
the observed surface does not cover that strip, so containment there cannot
be determined. Distances are exact point-to-triangle distances (interiors,
edges, and vertices) from a VTK static cell locator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np


SURFACE_ISOVALUE = 0.5
SURFACE_METHOD = "lewiner"
# Points this close to the surface (fraction of the smallest voxel spacing) count as on it.
SURFACE_TOLERANCE_VOXELS = 1e-6
HULL_TOLERANCE_VOXELS = 1e-9
SURFACE_PARAMETERS = (("isovalue", SURFACE_ISOVALUE), ("method", SURFACE_METHOD), ("smoothing", "none"))

Progress = Callable[[int | None, str], None]
AXIS_NAMES = ("i", "j", "k")


class SurfaceDistanceError(ValueError):
    """Raised when surface distance cannot be computed reliably."""


@dataclass(slots=True)
class ForegroundSurface:
    """Reconstructed foreground surface with a closest-point locator and an inside test."""

    mesh: Any
    locator: Any
    closure: Any
    enclosed: Any
    shape: tuple[int, int, int]
    affine: np.ndarray
    tolerance: float
    open_border_faces: tuple[str, ...]

    @property
    def triangle_count(self) -> int:
        """Triangles in the distance mesh."""
        return int(self.mesh.GetNumberOfCells())


def _polydata(vertices: np.ndarray, faces: np.ndarray) -> Any:
    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

    points = vtkPoints()
    points.SetDataTypeToDouble()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(vertices, dtype=np.float64), deep=True))
    cells = vtkCellArray()
    cells.SetData(3, numpy_to_vtkIdTypeArray(np.ascontiguousarray(faces.ravel(), dtype=np.int64), deep=True))
    mesh = vtkPolyData()
    mesh.SetPoints(points)
    mesh.SetPolys(cells)
    return mesh


def _marching_cubes(mask: np.ndarray, origin: np.ndarray, affine: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Isosurface of a binary block, returned in physical coordinates."""
    from skimage import measure

    try:
        vertices, faces, _normals, _values = measure.marching_cubes(
            mask.astype(np.float32), SURFACE_ISOVALUE, method=SURFACE_METHOD, allow_degenerate=False,
        )
    except (RuntimeError, ValueError):
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.int64)
    # Binary data at level 0.5 puts every vertex on an edge midpoint, which float32 stores exactly.
    index_points = vertices.astype(np.float64) + origin
    physical = index_points @ affine[:3, :3].T + affine[:3, 3]
    return physical, faces.astype(np.int64)


def _open_border_faces(mask: np.ndarray) -> tuple[str, ...]:
    faces = []
    for axis, name in enumerate(AXIS_NAMES):
        if np.take(mask, 0, axis=axis).any():
            faces.append(f"{name} = 0")
        if np.take(mask, mask.shape[axis] - 1, axis=axis).any():
            faces.append(f"{name} = {mask.shape[axis] - 1}")
    return tuple(faces)


def build_foreground_surface(
    mask: np.ndarray,
    affine: np.ndarray,
    spacing: tuple[float, float, float],
    progress: Progress | None = None,
) -> ForegroundSurface:
    """Reconstruct the unsmoothed 0.5 isosurface and prepare distance and inside queries."""
    from vtkmodules.vtkCommonDataModel import vtkStaticCellLocator
    from vtkmodules.vtkFiltersModeling import vtkSelectEnclosedPoints

    mask = np.asarray(mask, dtype=bool)
    affine = np.asarray(affine, dtype=float)
    if mask.ndim != 3 or min(mask.shape) < 2:
        raise SurfaceDistanceError(
            f"Surface reconstruction needs at least 2 voxels along every axis; the foreground shape is {mask.shape}."
        )
    if not mask.any() or mask.all():
        raise SurfaceDistanceError("The foreground has no foreground/background interface, so no surface can be reconstructed.")

    def update(message: str) -> None:
        if progress:
            progress(None, message)

    # Crop to the foreground bounding box plus one voxel where the image has it. That
    # margin is observed background, so no artificial boundary appears at crop edges.
    occupied = [np.flatnonzero(mask.any(axis=tuple(a for a in range(3) if a != axis))) for axis in range(3)]
    crop = tuple(slice(max(int(o[0]) - 1, 0), min(int(o[-1]) + 2, size)) for o, size in zip(occupied, mask.shape))
    origin = np.asarray([part.start for part in crop], dtype=np.float64)
    block = mask[crop]

    update(f"Reconstructing the unsmoothed {SURFACE_ISOVALUE} isosurface (marching cubes)")
    vertices, faces = _marching_cubes(block, origin, affine)
    if len(faces) == 0:
        raise SurfaceDistanceError("Marching cubes produced no surface triangles for this foreground.")
    mesh = _polydata(vertices, faces)

    update(f"Building a closed copy for inside tests and a closest-point locator ({len(faces)} triangles)")
    closure_vertices, closure_faces = _marching_cubes(np.pad(block, 1), origin - 1.0, affine)
    closure = _polydata(closure_vertices, closure_faces)
    if len(closure_faces) == 0 or not vtkSelectEnclosedPoints.IsSurfaceClosed(closure):
        raise SurfaceDistanceError(
            "The reconstructed surface could not be closed for inside/outside tests, so containment cannot be determined."
        )
    locator = vtkStaticCellLocator()
    locator.SetDataSet(mesh)
    locator.BuildLocator()
    tolerance = SURFACE_TOLERANCE_VOXELS * min(spacing)
    enclosed = vtkSelectEnclosedPoints()
    diagonal = float(np.linalg.norm(np.ptp(closure_vertices, axis=0))) or 1.0
    enclosed.SetTolerance(tolerance / diagonal)
    enclosed.Initialize(closure)
    return ForegroundSurface(
        mesh=mesh, locator=locator, closure=closure, enclosed=enclosed, shape=tuple(int(s) for s in mask.shape),
        affine=affine.copy(), tolerance=tolerance, open_border_faces=_open_border_faces(mask),
    )


def _closest_distances(surface: ForegroundSurface, points: np.ndarray) -> np.ndarray:
    from vtkmodules.vtkCommonCore import reference

    closest = [0.0, 0.0, 0.0]
    cell_id, sub_id, squared = reference(0), reference(0), reference(0.0)
    distances = np.empty(len(points))
    for index, point in enumerate(points):
        surface.locator.FindClosestPoint(point.tolist(), closest, cell_id, sub_id, squared)
        distances[index] = np.sqrt(squared.get())
    return distances


def surface_distances(
    surface: ForegroundSurface,
    voxel_positions: np.ndarray,
    node_ids: tuple[str, ...],
    progress: Progress | None = None,
) -> np.ndarray:
    """Distance from each node to the distance mesh, after surface-containment checks.

    Raises ``SurfaceDistanceError`` when a node lies beyond the voxel-centre
    hull or outside the reconstructed surface. Nodes within the tolerance of
    the surface are valid and get distance 0.
    """
    voxel_positions = np.asarray(voxel_positions, dtype=float).reshape((-1, 3))
    upper = np.asarray(surface.shape, dtype=float) - 1.0
    beyond = np.any((voxel_positions < -HULL_TOLERANCE_VOXELS) | (voxel_positions > upper + HULL_TOLERANCE_VOXELS), axis=1)
    if beyond.any():
        first = int(np.flatnonzero(beyond)[0])
        point = ", ".join(f"{value:g}" for value in voxel_positions[first])
        raise SurfaceDistanceError(
            f"Graph node '{node_ids[first]}' voxel_pos ({point}) lies beyond the outermost voxel centres "
            f"(valid range 0 to {tuple(int(v) for v in upper)}). The reconstructed surface does not cover this "
            "border strip, so containment cannot be determined. Use Voxel EDT for this graph."
        )
    points = voxel_positions @ surface.affine[:3, :3].T + surface.affine[:3, 3]
    if progress:
        progress(None, f"Measuring surface distance for {len(points)} nodes")
    distances = _closest_distances(surface, points)
    on_surface = distances <= surface.tolerance
    if progress:
        progress(None, "Checking that every node is inside the reconstructed surface")
    for index in np.flatnonzero(~on_surface):
        if not surface.enclosed.IsInsideSurface(points[index].tolist()):
            point = ", ".join(f"{value:g}" for value in voxel_positions[index])
            raise SurfaceDistanceError(
                f"Graph node '{node_ids[index]}' voxel_pos ({point}) is inside a foreground voxel cell but outside the "
                f"reconstructed {SURFACE_ISOVALUE} surface. Voxel-cell containment and surface containment differ "
                "near edges and corners, where the surface cuts across voxel cells. Use Voxel EDT for this graph."
            )
    distances[on_surface] = 0.0
    return distances


def file_identity(path: str | Path) -> tuple[str, int, int]:
    """Resolved path, modification time, and size, for cache keys."""
    resolved = Path(path).resolve()
    stat = resolved.stat()
    return str(resolved), int(stat.st_mtime_ns), int(stat.st_size)


class SurfaceCache:
    """Keeps the most recent foreground surface, keyed by file identity and surface parameters."""

    def __init__(self) -> None:
        self._key: tuple | None = None
        self._surface: ForegroundSurface | None = None
        self.builds = 0

    def get(self, key: tuple, build: Callable[[], ForegroundSurface]) -> tuple[ForegroundSurface, bool]:
        """Return ``(surface, reused)``, building and storing it when the key changed."""
        if self._surface is not None and self._key == key:
            return self._surface, True
        self.clear()
        surface = build()
        self._key, self._surface = key, surface
        self.builds += 1
        return surface, False

    def clear(self) -> None:
        """Drop the stored surface."""
        self._key = self._surface = None
