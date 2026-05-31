"""Connected-component helpers for Laplacian per-object execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, cast

import numpy as np
from scipy import ndimage

from .graph import GeometricGraph


_FULL_26_STRUCT = np.ones((3, 3, 3), dtype=np.uint8)


@dataclass(frozen=True, slots=True)
class LaplacianComponent:
    """One foreground connected component in full-volume coordinates."""

    label: int
    bbox: tuple[slice, slice, slice]
    voxel_count: int


def label_components(mask: np.ndarray) -> tuple[np.ndarray, list[LaplacianComponent]]:
    """Label a 3D foreground mask and return tight component descriptors."""
    binary = np.asarray(mask, dtype=bool)
    if binary.ndim != 3:
        raise ValueError("label_components expects a 3D mask.")

    labeled, count = cast(
        tuple[np.ndarray, int],
        ndimage.label(binary, structure=_FULL_26_STRUCT),
    )
    objects = ndimage.find_objects(labeled, max_label=count)

    components: list[LaplacianComponent] = []
    for index, bbox in enumerate(objects, start=1):
        if bbox is None:
            continue
        crop = labeled[bbox] == index
        voxel_count = int(np.count_nonzero(crop))
        if voxel_count:
            components.append(
                LaplacianComponent(
                    label=int(index),
                    bbox=cast(tuple[slice, slice, slice], bbox),
                    voxel_count=voxel_count,
                )
            )
    return labeled, components


def component_mask(labeled: np.ndarray, component: LaplacianComponent) -> np.ndarray:
    """Return a tight boolean crop for one labeled component."""
    return labeled[component.bbox] == component.label


def bbox_start(bbox: Sequence[slice]) -> np.ndarray:
    """Return the integer start offset for a bounding box."""
    return np.asarray([int(axis.start or 0) for axis in bbox], dtype=float)


def bbox_metadata(bbox: Sequence[slice]) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Return a JSON-friendly bbox representation."""
    return tuple((int(axis.start or 0), int(axis.stop or 0)) for axis in bbox)  # type: ignore[return-value]


def aggregate_component_graphs(
    component_graphs: Iterable[tuple[GeometricGraph, np.ndarray, int, int]],
) -> GeometricGraph | None:
    """Merge cropped component graphs into one full-volume graph."""
    aggregate = GeometricGraph()
    next_node = 0

    for graph, offset, component_index, component_label in component_graphs:
        node_mapping: dict[int, int] = {}
        for old_node in graph.GetNodes():
            new_node = next_node
            next_node += 1
            node_mapping[int(old_node)] = new_node

            attrs = _copy_node_attrs(graph.nodes[old_node])
            attrs["pos"] = np.asarray(attrs["pos"], dtype=float) + offset
            attrs["component_index"] = int(component_index)
            attrs["component_label"] = int(component_label)
            aggregate.add_node(new_node, **attrs)

        for edge_index, (u, v) in enumerate(graph.GetEdges()):
            new_u = node_mapping[int(u)]
            new_v = node_mapping[int(v)]
            attrs = _copy_edge_attrs(graph.edges[u, v])
            attrs["component_index"] = int(component_index)
            attrs["component_label"] = int(component_label)
            attrs["component_edge_index"] = int(edge_index)
            aggregate.add_edge(new_u, new_v, **attrs)

    if aggregate.number_of_nodes() == 0:
        return None
    return aggregate


def _copy_node_attrs(attrs: dict) -> dict:
    copied = {}
    for key, value in attrs.items():
        copied[key] = value.copy() if isinstance(value, np.ndarray) else value
    return copied


def _copy_edge_attrs(attrs: dict) -> dict:
    copied = {}
    for key, value in attrs.items():
        copied[key] = value.copy() if isinstance(value, np.ndarray) else value
    return copied
