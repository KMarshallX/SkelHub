"""Connected-component extraction for classified skeleton voxels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy import ndimage

from .classification import BRANCH, END, REGULAR

Voxel = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class SkeletonComponents:
    """Connected end, regular, and branch voxel groups."""

    endpoints: list[Voxel]
    branch_components: list[list[Voxel]]
    regular_components: list[list[Voxel]]


def _to_voxels(indices: np.ndarray) -> list[Voxel]:
    voxels = [tuple(int(v) for v in row) for row in indices]
    return sorted(voxels)


def _component_voxels(classes: np.ndarray, label: int) -> list[list[Voxel]]:
    structure = np.ones((3, 3, 3), dtype=np.uint8)
    labeled, count = ndimage.label(classes == label, structure=structure)
    components: list[list[Voxel]] = []
    for component_id in range(1, count + 1):
        indices = np.argwhere(labeled == component_id)
        if indices.size:
            components.append(_to_voxels(indices))
    return components


def _neighbor_offsets() -> list[Voxel]:
    return [
        (dx, dy, dz)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
        if (dx, dy, dz) != (0, 0, 0)
    ]


_OFFSETS = _neighbor_offsets()


def are_26_neighbors(a: Voxel, b: Voxel) -> bool:
    """Return whether two voxels touch in Voreen's 26-neighborhood."""
    return all(abs(a[i] - b[i]) <= 1 for i in range(3)) and a != b


def _component_adjacency(voxels: Iterable[Voxel]) -> dict[Voxel, list[Voxel]]:
    voxel_set = set(voxels)
    adjacency: dict[Voxel, list[Voxel]] = {voxel: [] for voxel in voxel_set}
    for x, y, z in voxel_set:
        for dx, dy, dz in _OFFSETS:
            neighbor = (x + dx, y + dy, z + dz)
            if neighbor in voxel_set:
                adjacency[(x, y, z)].append(neighbor)
    for neighbors in adjacency.values():
        neighbors.sort()
    return adjacency


def order_regular_component(voxels: list[Voxel]) -> list[Voxel]:
    """Order one regular component as a centerline path.

    Voreen preserves regular component order through run-tree merging. The
    Python port reconstructs that order from 26-neighbor adjacency.
    """
    if len(voxels) <= 1:
        return list(voxels)

    adjacency = _component_adjacency(voxels)
    endpoints = sorted(voxel for voxel, neighbors in adjacency.items() if len(neighbors) <= 1)
    start = endpoints[0] if endpoints else min(voxels)

    ordered: list[Voxel] = []
    visited: set[Voxel] = set()
    previous: Voxel | None = None
    current: Voxel | None = start

    while current is not None and current not in visited:
        ordered.append(current)
        visited.add(current)
        candidates = [neighbor for neighbor in adjacency[current] if neighbor != previous]
        unvisited = [neighbor for neighbor in candidates if neighbor not in visited]
        previous, current = current, unvisited[0] if unvisited else None

    if len(visited) != len(voxels):
        for voxel in sorted(set(voxels) - visited):
            ordered.append(voxel)
    return ordered


def extract_skeleton_components(classes: np.ndarray) -> SkeletonComponents:
    """Group classified voxels into Voreen-style component buckets."""
    end_components = _component_voxels(classes, int(END))
    endpoints = [component[0] for component in end_components if component]
    branch_components = _component_voxels(classes, int(BRANCH))
    regular_components = [
        order_regular_component(component)
        for component in _component_voxels(classes, int(REGULAR))
    ]
    return SkeletonComponents(
        endpoints=sorted(endpoints),
        branch_components=branch_components,
        regular_components=regular_components,
    )
