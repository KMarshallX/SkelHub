"""Multi-object decomposition, per-object execution, and merge helpers."""

from __future__ import annotations

import math
import time
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
    dilation_factor: float = 2.0,
    max_iterations: int = 200,
    min_size: int = 50,
    label_objects: bool = False,
    log: Callable[[str], None] | None = None,
) -> tuple[np.ndarray, dict]:
    """Run the full skeleton pipeline over all disconnected objects."""
    memberships = np.clip(np.asarray(volume, dtype=np.float32), 0.0, 1.0)
    if memberships.ndim != 3:
        raise ValueError("skeletonize_volume expects a 3D volume.")
    if dilation_factor <= 0.0:
        raise ValueError("dilation_factor must be positive.")
    if max_iterations < 0:
        raise ValueError("max_iterations must be non-negative.")

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

        object_start = time.perf_counter()
        skeleton_crop, metadata = extract_skeleton(
            cropped_volume,
            root_method=root_method,
            threshold_scale=threshold_scale,
            dilation_factor=dilation_factor,
            max_iterations=max_iterations,
            log=_object_log if log is not None else None,
        )
        object_elapsed = time.perf_counter() - object_start
        metadata["object_index"] = object_index
        metadata["component_label"] = component_label
        metadata["wall_clock_seconds"] = float(object_elapsed)

        skeleton_full = np.zeros_like(component_mask, dtype=bool)
        skeleton_full[bbox] = skeleton_crop
        results.append((component_label, skeleton_full))
        object_metadata.append(metadata)

        if log is not None:
            log(
                f"object {object_index}/{len(components)} complete: "
                f"iterations={metadata['iterations']}, "
                f"branches_added_per_iteration={metadata['branches_added_per_iteration']}, "
                f"total_branches={metadata['branch_count']}, "
                f"time={object_elapsed:.3f}s"
            )

    merged = merge_skeletons(memberships.shape, results, label_objects=label_objects)
    total_terminal_branches = int(sum(item["branch_count"] for item in object_metadata))
    avg_iterations = (
        float(np.mean([item["iterations"] for item in object_metadata]))
        if object_metadata
        else 0.0
    )
    max_iterations_hits = int(sum(bool(item["max_iterations_reached"]) for item in object_metadata))
    complexity_n = max(total_terminal_branches, 1)
    metadata = {
        "num_objects": len(components),
        "objects": object_metadata,
        "final_branch_count": total_terminal_branches,
        "average_iterations_per_object": avg_iterations,
        "max_iterations": int(max_iterations),
        "max_iterations_hits": max_iterations_hits,
        "complexity_reference": {
            "n_terminal_branches": total_terminal_branches,
            "log2_n": float(math.log2(complexity_n)),
            "sqrt_n": float(math.sqrt(complexity_n)),
        },
    }
    if log is not None:
        log(
            "final summary: "
            f"objects={metadata['num_objects']}, "
            f"total_branches={metadata['final_branch_count']}, "
            f"average_iterations_per_object={metadata['average_iterations_per_object']:.3f}, "
            f"max_iteration_hits={metadata['max_iterations_hits']}, "
            f"complexity_band=[log2(N)={metadata['complexity_reference']['log2_n']:.3f}, "
            f"sqrt(N)={metadata['complexity_reference']['sqrt_n']:.3f}] "
            f"for N={metadata['complexity_reference']['n_terminal_branches']}"
        )
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
