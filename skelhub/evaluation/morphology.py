"""Morphology-quality helpers for voxel-based skeleton evaluation."""

from __future__ import annotations

import numpy as np
from scipy import ndimage


FOREGROUND_CONNECTIVITY = 26
BACKGROUND_CONNECTIVITY = 6

_FOREGROUND_STRUCTURE = ndimage.generate_binary_structure(rank=3, connectivity=3)
_BACKGROUND_STRUCTURE = ndimage.generate_binary_structure(rank=3, connectivity=1)
_ENDPOINT_KERNEL = np.ones((3, 3, 3), dtype=np.int16)
_ENDPOINT_KERNEL[1, 1, 1] = 0


def count_object_components(volume: np.ndarray) -> int:
    """Count foreground connected components with 26-connectivity."""
    _, num_components = ndimage.label(np.asarray(volume, dtype=bool), structure=_FOREGROUND_STRUCTURE)
    return int(num_components)


def count_background_components(volume: np.ndarray) -> int:
    """Count background connected components with 6-connectivity."""
    background = ~np.asarray(volume, dtype=bool)
    _, num_components = ndimage.label(background, structure=_BACKGROUND_STRUCTURE)
    return int(num_components)


def count_endpoints(volume: np.ndarray) -> int:
    """Count voxel endpoints as degree-1 foreground voxels under the 26-neighborhood."""
    skeleton = np.asarray(volume, dtype=bool)
    neighbor_count = ndimage.convolve(
        skeleton.astype(np.int16, copy=False),
        _ENDPOINT_KERNEL,
        mode="constant",
        cval=0,
    )
    return int(np.count_nonzero(skeleton & (neighbor_count == 1)))


def compute_raw_morphology_metrics(
    pred_skeleton: np.ndarray,
    ref_skeleton: np.ndarray,
    warnings: list[str],
) -> tuple[dict[str, float], dict[str, int]]:
    """Compute signed raw morphology differences and supporting component counts."""
    pred_occ = count_object_components(pred_skeleton)
    ref_occ = count_object_components(ref_skeleton)
    pred_bcc = count_background_components(pred_skeleton)
    ref_bcc = count_background_components(ref_skeleton)
    pred_endpoints = count_endpoints(pred_skeleton)
    ref_endpoints = count_endpoints(ref_skeleton)

    raw_metrics = {
        "OCC": _signed_relative_difference(pred_occ, ref_occ, "OCC", warnings),
        "BCC": _signed_relative_difference(pred_bcc, ref_bcc, "BCC", warnings),
        "E": _signed_relative_difference(pred_endpoints, ref_endpoints, "E", warnings),
    }
    counts = {
        "pred_object_components": pred_occ,
        "ref_object_components": ref_occ,
        "pred_background_components": pred_bcc,
        "ref_background_components": ref_bcc,
        "pred_endpoints": pred_endpoints,
        "ref_endpoints": ref_endpoints,
    }
    return raw_metrics, counts


def clip_and_normalize_morphology(value: float) -> tuple[float, float]:
    """Clip a raw signed morphology value to [-5, 5] and convert it to a quality score."""
    clipped = float(np.clip(value, -5.0, 5.0))
    normalized = 1.0 - abs(clipped) / 5.0
    return clipped, normalized


def _signed_relative_difference(
    pred_count: int,
    ref_count: int,
    label: str,
    warnings: list[str],
) -> float:
    difference = float(pred_count - ref_count)
    if ref_count > 0:
        return difference / float(ref_count)
    if pred_count == 0:
        warnings.append(
            f"{label} reference count was zero for both skeletons; raw {label} was set to 0.0."
        )
        return 0.0

    warnings.append(
        f"{label} reference count was zero; raw {label} falls back to the signed count difference."
    )
    return difference
