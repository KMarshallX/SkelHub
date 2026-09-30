"""Local EDT ratio: a first centeredness indicator for skeleton samples.

For a skeleton point p with foreground EDT value D(p) (physical distance to
the nearest background voxel centre):

- search radius rho(p) = alpha * D(p), in physical units
- Q(p) = foreground voxel centres q in the same 26-connected foreground
  component as p with |p - q| <= rho(p)
- local_max(p) = max({D(p)} union {D(q) for q in Q(p)})
- ratio(p) = D(p) / local_max(p)

A ratio of 1 means no larger EDT was found nearby; it does not prove the
point lies on an anatomically correct centreline. For exact voxel-centre
samples the EDT is 1-Lipschitz, so 1 / (1 + alpha) <= ratio <= 1.

This module holds only numerics: no Qt, VTK, file dialogs, or algorithm
backends. The EDT and component labels are passed in, so callers can reuse
one calculation for many samples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from scipy import ndimage

from skelhub.core.models import SkeletonResult, VolumeData
from skelhub.postprocessing.checker import FOREGROUND_CELL_TOLERANCE


Progress = Callable[[int | None, str], None]

DEFAULT_ALPHA = 1.5
ALPHA_RANGE = (1.0, 3.0)
CONNECTIVITY = 26
# A candidate on the search sphere counts as inside when |p - q| <= rho * (1 + tolerance).
# 1e-6 absorbs the float32 precision of NIfTI affines (about 6e-8 relative), which
# would otherwise push candidates that lie exactly on the sphere just outside it.
BALL_RELATIVE_TOLERANCE = 1e-6
# A voxel centre within this distance (fraction of the smallest spacing) of p is p itself.
SELF_TOLERANCE_VOXELS = 1e-9
# Search balls may reach this far (in voxels) past the voxel-centre domain before a warning.
DOMAIN_TOLERANCE_VOXELS = 1e-9
DEFAULT_BATCH_SIZE = 256


class CenterednessError(ValueError):
    """Raised when centeredness inputs or parameters are invalid."""


@dataclass(slots=True, frozen=True)
class LocalEdtRatio:
    """Local EDT ratio for each sample, with the values it was built from.

    ``positions`` are voxel indices (fractional for graph nodes) in the full
    image. ``sample_edt``, ``local_max_edt``, and ``search_radii`` are in
    physical units; ``ratios`` are dimensionless. ``neighbour_counts`` counts
    same-component foreground voxel centres inside each search ball, not
    counting a voxel centre at the sample itself. ``extends_beyond_image``
    marks balls that reach past the voxel-centre domain ``[0, n - 1]``.
    """

    ratios: np.ndarray
    sample_edt: np.ndarray
    local_max_edt: np.ndarray
    search_radii: np.ndarray
    component_ids: np.ndarray
    neighbour_counts: np.ndarray
    extends_beyond_image: np.ndarray
    positions: np.ndarray
    alpha: float
    connectivity: int = CONNECTIVITY
    warnings: tuple[str, ...] = ()

    @property
    def sample_count(self) -> int:
        """Number of samples."""
        return int(self.ratios.shape[0])

    @property
    def limited_support(self) -> np.ndarray:
        """Samples whose maximum rests on D(p) alone: no other candidate was in the ball."""
        return self.neighbour_counts == 0


def validate_alpha(alpha: object) -> float:
    """Return alpha as a float, or raise when it is not finite or outside ``ALPHA_RANGE``."""
    low, high = ALPHA_RANGE
    if isinstance(alpha, bool):
        raise CenterednessError(f"Radius multiplier alpha must be a number; got {alpha!r}.")
    try:
        value = float(alpha)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise CenterednessError(f"Radius multiplier alpha must be a number; got {alpha!r}.") from exc
    if not np.isfinite(value):
        raise CenterednessError(f"Radius multiplier alpha must be finite; got {value}.")
    if not low <= value <= high:
        raise CenterednessError(f"Radius multiplier alpha must be between {low:g} and {high:g}; got {value:g}.")
    return value


def label_foreground_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Label 26-connected foreground components; background is 0.

    Face-, edge-, and corner-touching voxels share a component.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 3:
        raise CenterednessError(f"Foreground must be 3D; got {mask.ndim}D.")
    labels, count = ndimage.label(mask, structure=np.ones((3, 3, 3), dtype=bool))
    return labels, int(count)


def _local_label(labels: np.ndarray, indices: np.ndarray, origin: np.ndarray) -> np.ndarray:
    """Labels at full-image integer indices; indices outside the label block read 0 (background)."""
    local = indices - origin
    inside = np.all((local >= 0) & (local < np.asarray(labels.shape)), axis=1)
    values = np.zeros(len(indices), dtype=labels.dtype)
    values[inside] = labels[tuple(local[inside].T)]
    return values


def component_ids_at_voxels(
    labels: np.ndarray,
    voxels: np.ndarray,
    origin: Sequence[int] = (0, 0, 0),
) -> np.ndarray:
    """Component label at each integer voxel; every voxel must be foreground."""
    voxels = np.asarray(voxels, dtype=np.int64).reshape((-1, 3))
    ids = _local_label(labels, voxels, np.asarray(origin, dtype=np.int64))
    if np.any(ids == 0):
        first = tuple(int(value) for value in voxels[int(np.flatnonzero(ids == 0)[0])])
        raise CenterednessError(f"Skeleton voxel {first} is not foreground, so it has no foreground component.")
    return ids


def component_ids_at_points(
    labels: np.ndarray,
    points: np.ndarray,
    origin: Sequence[int] = (0, 0, 0),
    sample_names: Sequence[str] | None = None,
) -> np.ndarray:
    """Component label for fractional voxel-space points, by foreground-cell containment.

    Uses the checker convention: voxel ``c`` is the closed cell ``[c - 0.5, c + 0.5]``
    per axis. A point on a shared face, edge, or corner is checked against every
    cell that contains it. A point with no foreground cell, or with foreground
    cells from different components, is rejected; nothing is rounded.
    """
    points = np.asarray(points, dtype=float).reshape((-1, 3))
    origin_array = np.asarray(origin, dtype=np.int64)
    cell_radius = 0.5 + FOREGROUND_CELL_TOLERANCE
    lowest = np.ceil(points - cell_radius).astype(np.int64)
    highest = np.floor(points + cell_radius).astype(np.int64)
    found = np.zeros((len(points), 8), dtype=labels.dtype)
    for column, offset in enumerate(np.ndindex(2, 2, 2)):
        candidates = lowest + np.asarray(offset, dtype=np.int64)
        valid = np.all(candidates <= highest, axis=1)
        found[valid, column] = _local_label(labels, candidates[valid], origin_array)

    def name(index: int) -> str:
        return f"Graph node '{sample_names[index]}'" if sample_names is not None else f"Sample {index}"

    largest = found.max(axis=1)
    if np.any(largest == 0):
        first = int(np.flatnonzero(largest == 0)[0])
        raise CenterednessError(f"{name(first)} at voxel position {tuple(points[first])} lies in no foreground cell.")
    smallest = np.where(found > 0, found, largest[:, None]).min(axis=1)
    if np.any(smallest != largest):
        first = int(np.flatnonzero(smallest != largest)[0])
        raise CenterednessError(
            f"{name(first)} at voxel position {tuple(points[first])} touches foreground cells from different "
            "components; its component is ambiguous."
        )
    return largest


def _validate_kernel_inputs(
    edt: np.ndarray,
    labels: np.ndarray,
    positions: np.ndarray,
    sample_edt: np.ndarray,
    component_ids: np.ndarray,
    spacing: np.ndarray,
    image_shape: np.ndarray,
    sample_names: Sequence[str] | None,
) -> None:
    if edt.ndim != 3 or edt.shape != labels.shape:
        raise CenterednessError(f"EDT and component labels must be 3D with one shape; got {edt.shape} and {labels.shape}.")
    count = len(positions)
    if positions.shape != (count, 3) or not np.isfinite(positions).all():
        raise CenterednessError("Sample positions must be finite voxel-space points of shape (N, 3).")
    if sample_edt.shape != (count,) or component_ids.shape != (count,):
        raise CenterednessError("Sample EDT values and component ids must have one entry per sample.")
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise CenterednessError(f"Voxel spacing must be three positive finite values; got {tuple(spacing)}.")
    if image_shape.shape != (3,) or np.any(image_shape < 1):
        raise CenterednessError(f"Image shape must be three positive sizes; got {tuple(image_shape)}.")
    bad = ~np.isfinite(sample_edt) | (sample_edt <= 0)
    if np.any(bad):
        first = int(np.flatnonzero(bad)[0])
        label = f"graph node '{sample_names[first]}'" if sample_names is not None else f"sample {first}"
        raise CenterednessError(
            f"EDT at {label} is {sample_edt[first]:g}; the local EDT ratio needs a positive, finite EDT."
        )
    if np.any(component_ids <= 0):
        raise CenterednessError("Every sample needs a positive foreground component id.")


def local_edt_ratio(
    edt: np.ndarray,
    labels: np.ndarray,
    positions: np.ndarray,
    sample_edt: np.ndarray,
    component_ids: np.ndarray,
    spacing: Sequence[float],
    alpha: float = DEFAULT_ALPHA,
    *,
    origin: Sequence[int] = (0, 0, 0),
    image_shape: Sequence[int] | None = None,
    progress: Progress | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sample_names: Sequence[str] | None = None,
) -> LocalEdtRatio:
    """Compute the local EDT ratio at each sample by exact spherical search.

    ``edt`` and ``labels`` cover the block that starts at ``origin`` in the full
    image of shape ``image_shape`` (default: the block itself). The block must
    contain every foreground voxel, as the padded crop from
    ``skelhub.postprocessing.edt.foreground_edt`` does, so clipping a search to
    it only drops background. ``positions`` are full-image voxel indices;
    ``spacing`` holds the physical length of each voxel axis, whose axes must be
    orthogonal (rotations are fine; shear is not).

    For each sample, a voxel box bounds the ball, then candidates are kept only
    if their physical distance is within the radius and they share the
    sample's component. No sample-by-volume distance array is built.
    ``progress`` receives the percentage of samples done after each batch.
    """
    alpha = validate_alpha(alpha)
    edt = np.asarray(edt, dtype=float)
    labels = np.asarray(labels)
    positions = np.asarray(positions, dtype=float).reshape((-1, 3))
    sample_edt = np.asarray(sample_edt, dtype=float).reshape(-1)
    component_ids = np.asarray(component_ids).reshape(-1)
    spacing_array = np.asarray(spacing, dtype=float).reshape(-1)
    origin_array = np.asarray(origin, dtype=np.int64).reshape(-1)
    shape_array = np.asarray(edt.shape if image_shape is None else image_shape, dtype=np.int64).reshape(-1)
    _validate_kernel_inputs(edt, labels, positions, sample_edt, component_ids, spacing_array, shape_array, sample_names)
    if int(batch_size) < 1:
        raise CenterednessError(f"Batch size must be positive; got {batch_size}.")

    count = len(positions)
    radii = alpha * sample_edt
    local_max = sample_edt.copy()
    neighbours = np.zeros(count, dtype=np.int64)
    self_tolerance_sq = (SELF_TOLERANCE_VOXELS * float(spacing_array.min())) ** 2
    block_upper = np.asarray(edt.shape, dtype=np.int64) - 1
    local_positions = positions - origin_array

    # Ball extent in voxels per axis; valid because the voxel axes are orthogonal.
    half_widths = radii[:, None] / spacing_array
    extends = np.any(
        (positions - half_widths < -DOMAIN_TOLERANCE_VOXELS)
        | (positions + half_widths > (shape_array - 1) + DOMAIN_TOLERANCE_VOXELS),
        axis=1,
    )

    # Search boxes for all samples at once, clipped to the block; plain lists keep the loop light.
    reach = half_widths * (1.0 + BALL_RELATIVE_TOLERANCE)
    lows = np.maximum(np.ceil(local_positions - reach), 0).astype(np.int64).tolist()
    highs = np.minimum(np.floor(local_positions + reach), block_upper).astype(np.int64).tolist()
    radius_sq = ((radii * (1.0 + BALL_RELATIVE_TOLERANCE)) ** 2).tolist()
    centres = local_positions.tolist()
    targets = component_ids.tolist()
    spacing_list = spacing_array.tolist()

    for start in range(0, count, int(batch_size)):
        stop = min(start + int(batch_size), count)
        for index in range(start, stop):
            low, high, centre = lows[index], highs[index], centres[index]
            if low[0] > high[0] or low[1] > high[1] or low[2] > high[2]:
                continue
            dx, dy, dz = (
                ((np.arange(low[axis], high[axis] + 1) - centre[axis]) * spacing_list[axis]) ** 2 for axis in range(3)
            )
            distance_sq = dx[:, None, None] + dy[None, :, None] + dz[None, None, :]
            box = (slice(low[0], high[0] + 1), slice(low[1], high[1] + 1), slice(low[2], high[2] + 1))
            candidates = (distance_sq <= radius_sq[index]) & (labels[box] == targets[index])
            if not candidates.any():
                continue
            neighbours[index] = int(np.count_nonzero(candidates & (distance_sq > self_tolerance_sq)))
            local_max[index] = max(local_max[index], float(np.max(edt[box], where=candidates, initial=-np.inf)))
        if progress is not None:
            progress(int(100 * stop / count), f"Local EDT ratio: {stop} of {count} samples (α = {alpha:g})")

    ratios = sample_edt / local_max
    warnings = []
    beyond = int(np.count_nonzero(extends))
    if beyond:
        warnings.append(
            f"{beyond} of {count} search balls reach beyond the image's voxel-centre domain. "
            "The maximum uses observed voxels only; a larger EDT outside the image could be missed."
        )
    limited = int(np.count_nonzero(neighbours == 0))
    if limited:
        warnings.append(
            f"{limited} of {count} samples found no other same-component foreground voxel centre within "
            "their search radius (limited neighbourhood support); their ratio is 1 by definition."
        )
    return LocalEdtRatio(
        ratios=ratios,
        sample_edt=sample_edt,
        local_max_edt=local_max,
        search_radii=radii,
        component_ids=component_ids.astype(np.int64),
        neighbour_counts=neighbours,
        extends_beyond_image=extends,
        positions=positions,
        alpha=alpha,
        connectivity=CONNECTIVITY,
        warnings=tuple(warnings),
    )


def local_edt_ratio_for_skeleton(
    skeleton: SkeletonResult,
    foreground: VolumeData,
    alpha: float = DEFAULT_ALPHA,
    *,
    progress: Progress | None = None,
) -> LocalEdtRatio:
    """Local EDT ratio at every voxel of a ``SkeletonResult`` skeleton.

    ``foreground`` supplies the binary mask and the affine; spacing comes from
    the affine's column lengths. The skeleton must share the foreground grid
    and lie inside the foreground. Samples follow ``np.argwhere`` order.
    """
    from skelhub.postprocessing.edt import EdtInputError, foreground_edt, voxel_spacing_from_affine

    alpha = validate_alpha(alpha)
    mask = np.asarray(foreground.data)
    skeleton_mask = np.asarray(skeleton.skeleton)
    for label, data in (("Foreground", mask), ("Skeleton", skeleton_mask)):
        if data.ndim != 3:
            raise CenterednessError(f"{label} must be 3D; got {data.ndim}D.")
        if not np.isin(data, (0, 1)).all():
            raise CenterednessError(f"{label} must be binary (0 and 1 only).")
    if mask.shape != skeleton_mask.shape:
        raise CenterednessError(f"Foreground and skeleton shapes differ: {mask.shape} != {skeleton_mask.shape}.")
    mask = mask.astype(bool)
    skeleton_mask = skeleton_mask.astype(bool)
    if not skeleton_mask.any():
        raise CenterednessError("Skeleton is empty; there is nothing to sample.")
    if np.any(skeleton_mask & ~mask):
        raise CenterednessError("Some skeleton voxels lie outside the foreground.")
    try:
        spacing = voxel_spacing_from_affine(foreground.affine)
        edt, origin = foreground_edt(mask, spacing)
    except EdtInputError as exc:
        raise CenterednessError(str(exc)) from exc
    crop = tuple(slice(start, start + size) for start, size in zip(origin, edt.shape))
    labels, _count = label_foreground_components(mask[crop])
    voxels = np.argwhere(skeleton_mask)
    local = voxels - np.asarray(origin)
    return local_edt_ratio(
        edt, labels, voxels, edt[tuple(local.T)], component_ids_at_voxels(labels, voxels, origin),
        spacing, alpha, origin=origin, image_shape=mask.shape, progress=progress,
    )
