"""Geometry helpers extracted and modernized from VascGraph."""

from __future__ import annotations

import networkx as nx
import numpy as np
import scipy.ndimage as ndi


def assign_to_clusters(pos: np.ndarray, resolution: float = 1.0):
    """Group positions by rounded spatial bins and return centroids and indices."""
    scaled = np.asarray(pos, dtype=float) / float(resolution)
    clusters_init = np.round(scaled).astype(int)
    _, inverse, counts = np.unique(
        clusters_init,
        axis=0,
        return_inverse=True,
        return_counts=True,
    )
    cluster_ids = np.where(counts >= 1)[0]
    clusters_points = [np.where(inverse == cluster_id)[0] for cluster_id in cluster_ids]

    original_scale = scaled * float(resolution)
    clusters_pos = [original_scale[indices] for indices in clusters_points]
    centroids = [np.mean(points, axis=0) for points in clusters_pos]
    return centroids, clusters_pos, clusters_points


def cycle_area(corners) -> float:
    """Return polygon area for a 3D cycle."""
    corners = np.asarray(corners, dtype=float)
    if corners.size == 0:
        return 0.0
    cross = np.zeros(3, dtype=float)
    for idx in range(len(corners)):
        cross += np.cross(corners[idx], corners[(idx + 1) % len(corners)])
    return float(np.linalg.norm(cross) / 2.0)


def cycle_area_all(corners) -> np.ndarray | int:
    """Vectorized polygon area for a batch of cycles."""
    corners = np.asarray(corners, dtype=float)
    if corners.size == 0:
        return 0
    cross = np.zeros((corners.shape[0], corners.shape[2]), dtype=float)
    for idx in range(corners.shape[1]):
        cross += np.cross(corners[:, idx], corners[:, (idx + 1) % corners.shape[1]])
    return np.linalg.norm(cross, axis=1) / 2.0


def _check_node(pos: np.ndarray, neighbor_pos: np.ndarray, threshold: float = 0.0) -> bool:
    if len(neighbor_pos) < 2:
        return False
    p1 = neighbor_pos[0]
    p2 = neighbor_pos[1:]
    vec1 = p1 - pos
    vec2 = p2 - pos
    norm1 = float(np.linalg.norm(vec1))
    norm2 = np.linalg.norm(vec2, axis=1)
    cosine = np.ones_like(norm2, dtype=float)
    mask = (norm1 > 0.0) & (norm2 > 0.0)
    cosine[mask] = np.dot(vec2[mask], vec1) / (norm1 * norm2[mask])
    cosine[(cosine < -1.0) | (cosine > 1.0)] = 0.0
    angle = np.degrees(np.arccos(cosine))
    threshold_high = 180.0 - threshold
    return not np.any((angle > threshold) & (angle < threshold_high))


def is_skeleton_nodes(pos: np.ndarray, neighbor_pos, threshold: float = 0.0) -> np.ndarray:
    """Return True for nodes that satisfy VascGraph's local angle skeleton test."""
    return np.asarray(
        [_check_node(point, np.asarray(neighbors, dtype=float), threshold) for point, neighbors in zip(pos, neighbor_pos)],
        dtype=bool,
    )


def fix_graph(graph, copy: bool = True):
    """Relabel graph nodes to contiguous integer ids."""
    old_nodes = list(graph.GetNodes())
    mapping = {old_node: new_node for new_node, old_node in enumerate(old_nodes)}
    fixed = nx.relabel_nodes(graph, mapping, copy=copy)
    if hasattr(fixed, "Area"):
        fixed.Area = getattr(graph, "Area", 0)
    return fixed


def numpy_fill(data, lengths, vector_size: int | None = None):
    """Pad ragged row data into a dense array and validity mask."""
    lengths = np.asarray(lengths, dtype=int)
    if lengths.size == 0:
        raise ValueError("Cannot pad empty ragged data.")
    max_len = int(lengths.max(initial=0))
    mask = np.arange(max_len) < lengths[:, None]
    if vector_size:
        out = np.zeros((mask.shape[0], mask.shape[1], vector_size), dtype=float)
        if np.any(mask):
            out[mask, :] = np.concatenate([np.asarray(row, dtype=float) for row in data if len(row)])
    else:
        out = np.zeros((mask.shape[0], mask.shape[1]), dtype=float)
        if np.any(mask):
            out[mask] = np.concatenate([np.asarray(row, dtype=float) for row in data if len(row)])
    return out, mask


def distance_map_3d(label: np.ndarray) -> np.ndarray:
    """Compute a 3D Euclidean distance transform for the foreground mask."""
    return ndi.distance_transform_edt(np.asarray(label) > 0)


def post_node_cleaning(graph):
    """Remove degree-2 nodes while preserving graph continuity."""
    cleaned = graph.copy()
    changed = True
    while changed:
        changed = False
        for node in list(cleaned.GetNodes()):
            neighbors = cleaned.GetNeighbors(node)
            if len(neighbors) == 2:
                cleaned.remove_node(node)
                if neighbors[0] != neighbors[1]:
                    cleaned.add_edge(neighbors[0], neighbors[1])
                changed = True
                break
    return fix_graph(cleaned)
