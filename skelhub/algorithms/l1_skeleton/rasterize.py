"""Rasterization helpers for L1 contracted samples and branch curves."""

from __future__ import annotations

import numpy as np

from .skeleton import Branch


def rasterize_l1_points(points: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    """Rasterize contracted L1 sample points into a binary skeleton volume."""
    skeleton = np.zeros(shape, dtype=np.uint8)
    if len(points) == 0:
        return skeleton

    rounded_points = np.rint(points).astype(int)
    for node in rounded_points:
        if np.all(node >= 0) and np.all(node < np.asarray(shape)):
            skeleton[tuple(node)] = 1
    return skeleton


def rasterize_l1_branches(branches: list[Branch], shape: tuple[int, int, int]) -> np.ndarray:
    """Rasterize L1 branch curves into a binary 26-connected skeleton volume."""
    skeleton = np.zeros(shape, dtype=np.uint8)
    for branch in branches:
        points = np.asarray(branch.points, dtype=float)
        if len(points) == 0:
            continue
        if len(points) == 1:
            _mark_voxel(skeleton, np.rint(points[0]).astype(int))
            continue
        for start, end in zip(points[:-1], points[1:]):
            for voxel in _line_voxels(start, end):
                _mark_voxel(skeleton, voxel)
    return skeleton


def _line_voxels(start: np.ndarray, end: np.ndarray) -> list[np.ndarray]:
    """Sample a line segment densely enough to produce connected rounded voxels."""
    delta = np.asarray(end, dtype=float) - np.asarray(start, dtype=float)
    steps = max(int(np.ceil(np.max(np.abs(delta)))) * 2, 1)
    return [np.rint(start + delta * (idx / steps)).astype(int) for idx in range(steps + 1)]


def _mark_voxel(skeleton: np.ndarray, voxel: np.ndarray) -> None:
    """Mark one voxel if it is inside the output volume."""
    if np.all(voxel >= 0) and np.all(voxel < np.asarray(skeleton.shape)):
        skeleton[tuple(voxel)] = 1
