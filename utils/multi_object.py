"""Multi-object decomposition, per-object execution, and merge helpers."""

from __future__ import annotations

from typing import Callable, List, Sequence, Tuple, cast

import numpy as np
from scipy import ndimage

from core.skeleton import extract_skeleton


_FULL_26_STRUCT = np.ones((3, 3, 3), dtype=np.uint8)


def decompose(volume: np.ndarray, min_size: int = 50) -> List[Tuple[int, np.ndarray]]:
    """Decompose volume into 26-connected components.

    Parameters
    ----------
    volume
        Fuzzy or binary input volume in `(z, y, x)` order.
    min_size
        Minimum voxel count required for a component to be kept.

    Returns
    -------
    list
        List of `(component_label, sub_mask)` tuples where `sub_mask` is a
        boolean mask in full-volume coordinates.
    """
    object_mask = np.asarray(volume) > 0
    labeled, num_components = cast(
        Tuple[np.ndarray, int], ndimage.label(object_mask, structure=_FULL_26_STRUCT)
    )

    components: List[Tuple[int, np.ndarray]] = []
    for component_label in range(1, num_components + 1):
        sub_mask = labeled == component_label
        if int(sub_mask.sum()) >= int(min_size):
            components.append((component_label, sub_mask))

    return components


def _bounding_box(mask: np.ndarray) -> tuple[slice, slice, slice]:
    """Return the tight bounding box of a boolean mask."""
    coords = np.argwhere(mask)
    if coords.size == 0:
        return (slice(0, 0), slice(0, 0), slice(0, 0))
    mins = coords.min(axis=0)
    maxs = coords.max(axis=0) + 1
    return tuple(slice(int(start), int(stop)) for start, stop in zip(mins, maxs, strict=True))


def skeletonize_volume(
    volume: np.ndarray,
    root_method: str = "max_fdt",
    threshold_scale: float = 1.0,
    min_size: int = 50,
    label_objects: bool = False,
    log: Callable[[str], None] | None = None,
) -> tuple[np.ndarray, dict]:
    """Run the full Milestone 6 skeleton pipeline over all disconnected objects."""
    memberships = np.clip(np.asarray(volume, dtype=np.float32), 0.0, 1.0)
    if memberships.ndim != 3:
        raise ValueError("skeletonize_volume expects a 3D volume.")

    components = decompose(memberships, min_size=min_size)
    if log is not None:
        log(f"{len(components)} object(s) found")

    results: List[Tuple[int, np.ndarray]] = []
    object_metadata: list[dict] = []

    for object_index, (component_label, component_mask) in enumerate(components, start=1):
        bbox = _bounding_box(component_mask)
        cropped_mask = component_mask[bbox]
        cropped_volume = np.where(cropped_mask, memberships[bbox], 0.0).astype(np.float32, copy=False)

        def _object_log(message: str) -> None:
            if log is not None:
                log(f"object {object_index}/{len(components)} (label={component_label}): {message}")

        skeleton_crop, metadata = extract_skeleton(
            cropped_volume,
            root_method=root_method,
            threshold_scale=threshold_scale,
            log=_object_log if log is not None else None,
        )

        skeleton_full = np.zeros_like(component_mask, dtype=bool)
        skeleton_full[bbox] = skeleton_crop
        results.append((component_label, skeleton_full))
        object_metadata.append(metadata)

        if log is not None:
            log(
                f"object {object_index}/{len(components)} complete: "
                f"{metadata['branch_count']} skeletal branch(es)"
            )

    merged = merge_skeletons(memberships.shape, results, label_objects=label_objects)
    metadata = {
        "num_objects": len(components),
        "objects": object_metadata,
        "final_branch_count": int(sum(item["branch_count"] for item in object_metadata)),
    }
    if log is not None:
        log(f"final number of skeletal branches detected: {metadata['final_branch_count']}")
    return merged, metadata


def merge_skeletons(
    shape: Sequence[int],
    results: Sequence[Tuple[int, np.ndarray]],
    label_objects: bool = False,
) -> np.ndarray:
    """Merge per-object skeleton masks into a single volume.

    Parameters
    ----------
    shape
        Output array shape `(z, y, x)`.
    results
        Sequence of `(label, skeleton_mask)` tuples.
    label_objects
        If True, voxels get their object label value; otherwise they are set to 1.

    Returns
    -------
    np.ndarray
        Merged skeleton volume.
    """
    dtype = np.int32 if label_objects else np.uint8
    merged = np.zeros(shape, dtype=dtype)

    for label, skeleton_mask in results:
        mask = np.asarray(skeleton_mask, dtype=bool)
        if label_objects:
            merged[mask] = int(label)
        else:
            merged[mask] = 1

    return merged
