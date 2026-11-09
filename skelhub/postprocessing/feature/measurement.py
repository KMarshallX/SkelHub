"""Geometry and radius measurements for vessel branches."""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from .assignment import assign_foreground_to_edges
from .models import FeatureEdgeRecord, FeatureGraph, FeatureNodeRecord
from .sampling import edge_samples

_SURFACE_STRUCTURE = ndimage.generate_binary_structure(3, 1)


def _polyline_length(points: np.ndarray, scale: np.ndarray) -> float:
    """Length of an oriented point path that already starts and ends at its nodes."""
    scaled = np.asarray(points, dtype=float) * scale
    return float(np.linalg.norm(np.diff(scaled, axis=0), axis=1).sum())


def _length(path: np.ndarray, begin: np.ndarray, end: np.ndarray, scale: np.ndarray) -> float:
    """Length from ``begin`` through stored centreline voxels to ``end``."""
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
    samples: list[np.ndarray],
    labels: np.ndarray,
    scale: np.ndarray,
    offset: float,
) -> list[tuple[float, float, float]]:
    """Per edge: mean over samples of each sample's min, mean and max surface distance."""
    surface = foreground & ~ndimage.binary_erosion(foreground, structure=_SURFACE_STRUCTURE, border_value=0)
    result: list[tuple[float, float, float]] = []
    for edge_index, edge_path in enumerate(samples):
        if edge_path.size == 0:
            result.append((math.nan, math.nan, math.nan))
            continue
        path = np.asarray(edge_path, dtype=float) * scale
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
    sampling_step: float | None = None,
) -> tuple[tuple[FeatureEdgeRecord, ...], tuple[FeatureNodeRecord, ...]]:
    """Calculate voxel-space and header-scaled feature rows.

    ``sampling_step`` (voxels) spaces the radius samples along
    ``centerline_voxel_points``; it is ignored for ``centerline_voxels``. Both
    measurement spaces use the same voxel-space samples, scaled by ``zooms``.
    """
    voxel_scale = np.ones(3, dtype=float)
    image_scale = np.asarray(zooms, dtype=float)
    samples = edge_samples(graph, sampling_step)
    voxel_labels = assign_foreground_to_edges(foreground, graph, samples, voxel_scale)
    image_labels = assign_foreground_to_edges(foreground, graph, samples, image_scale)
    voxel_radii = _radius_values(foreground, samples, voxel_labels, voxel_scale, 0.5)
    image_radii = _radius_values(foreground, samples, image_labels, image_scale, float(np.mean(image_scale)) / 2.0)

    node_by_id = {node.id: node for node in graph.nodes}
    degrees = {node.id: 0 for node in graph.nodes}
    for edge in graph.edges:
        degrees[edge.node1_id] += 1
        degrees[edge.node2_id] += 1

    records: list[FeatureEdgeRecord] = []
    for index, edge in enumerate(graph.edges):
        begin = node_by_id[edge.node1_id].voxel_pos
        end = node_by_id[edge.node2_id].voxel_pos
        if graph.uses_centerline_points:
            voxel_length = _polyline_length(edge.path, voxel_scale)
            image_length = _polyline_length(edge.path, image_scale)
        else:
            voxel_length = _length(edge.path, begin, end, voxel_scale)
            image_length = _length(edge.path, begin, end, image_scale)
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
