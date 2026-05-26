"""Geometry and radius measurements for vessel branches."""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from .assignment import assign_foreground_to_edges
from .models import FeatureEdgeRecord, FeatureGraph, FeatureNodeRecord

_SURFACE_STRUCTURE = ndimage.generate_binary_structure(3, 1)


def _length(path: np.ndarray, begin: np.ndarray, end: np.ndarray, scale: np.ndarray) -> float:
    scaled_begin = begin * scale
    scaled_end = end * scale
    if path.size == 0:
        return float(np.linalg.norm(scaled_end - scaled_begin))
    scaled_path = path.astype(float) * scale
    points = np.vstack((scaled_begin, scaled_path, scaled_end))
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def _curveness(length: float, begin: np.ndarray, end: np.ndarray, scale: np.ndarray) -> float:
    distance = float(np.linalg.norm((end - begin) * scale))
    return math.inf if distance == 0.0 else length / distance


def _radius_values(
    foreground: np.ndarray,
    graph: FeatureGraph,
    labels: np.ndarray,
    scale: np.ndarray,
    offset: float,
) -> list[tuple[float, float, float]]:
    surface = foreground & ~ndimage.binary_erosion(foreground, structure=_SURFACE_STRUCTURE, border_value=0)
    result: list[tuple[float, float, float]] = []
    for edge_index, edge in enumerate(graph.edges):
        if edge.centerline_voxels.size == 0:
            result.append((math.nan, math.nan, math.nan))
            continue
        path = edge.centerline_voxels.astype(float) * scale
        tree = cKDTree(path)
        sample_observations: list[list[float]] = [[] for _ in range(len(path))]
        for voxel in np.argwhere(surface & (labels == edge_index)):
            point = voxel.astype(float) * scale
            distance, _ = tree.query(point)
            nearest = tree.query_ball_point(point, float(distance) + 1e-10)
            for sample_index in nearest:
                measured = float(np.linalg.norm(path[sample_index] - point))
                if np.isclose(measured, distance, rtol=0.0, atol=1e-9):
                    sample_observations[sample_index].append(measured + offset)
        valid = [values for values in sample_observations if values]
        if not valid:
            result.append((math.nan, math.nan, math.nan))
            continue
        result.append(
            (
                float(np.mean([min(values) for values in valid])),
                float(np.mean([np.mean(values) for values in valid])),
                float(np.mean([max(values) for values in valid])),
            )
        )
    return result


def calculate_feature_records(
    foreground: np.ndarray,
    graph: FeatureGraph,
    zooms: tuple[float, float, float],
) -> tuple[tuple[FeatureEdgeRecord, ...], tuple[FeatureNodeRecord, ...]]:
    """Calculate voxel-space and header-scaled feature rows."""
    voxel_scale = np.ones(3, dtype=float)
    image_scale = np.asarray(zooms, dtype=float)
    voxel_labels = assign_foreground_to_edges(foreground, graph, voxel_scale)
    image_labels = assign_foreground_to_edges(foreground, graph, image_scale)
    voxel_radii = _radius_values(foreground, graph, voxel_labels, voxel_scale, 0.5)
    image_radii = _radius_values(foreground, graph, image_labels, image_scale, float(np.mean(image_scale)) / 2.0)

    node_by_id = {node.id: node for node in graph.nodes}
    degrees = {node.id: 0 for node in graph.nodes}
    for edge in graph.edges:
        degrees[edge.node1_id] += 1
        degrees[edge.node2_id] += 1

    records: list[FeatureEdgeRecord] = []
    for index, edge in enumerate(graph.edges):
        begin = node_by_id[edge.node1_id].voxel_pos
        end = node_by_id[edge.node2_id].voxel_pos
        voxel_length = _length(edge.centerline_voxels, begin, end, voxel_scale)
        image_length = _length(edge.centerline_voxels, begin, end, image_scale)
        records.append(
            FeatureEdgeRecord(
                id=edge.id,
                node1_id=edge.node1_id,
                node2_id=edge.node2_id,
                length=voxel_length,
                minRadius=voxel_radii[index][0],
                avgRadius=voxel_radii[index][1],
                maxRadius=voxel_radii[index][2],
                curveness=_curveness(voxel_length, begin, end, voxel_scale),
                node1_degree=degrees[edge.node1_id],
                node2_degree=degrees[edge.node2_id],
                length_image=image_length,
                minRadius_image=image_radii[index][0],
                avgRadius_image=image_radii[index][1],
                maxRadius_image=image_radii[index][2],
                curveness_image=_curveness(image_length, begin, end, image_scale),
            )
        )
    nodes = tuple(
        FeatureNodeRecord(
            node.id,
            float(node.voxel_pos[0]),
            float(node.voxel_pos[1]),
            float(node.voxel_pos[2]),
            degrees[node.id],
        )
        for node in graph.nodes
    )
    return tuple(records), nodes
