"""Core Python implementation of the L1-medial skeleton v1 flow."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from .config import L1SkeletonConfig


@dataclass(slots=True)
class L1RunResult:
    """Internal L1 skeletonization result."""

    points: np.ndarray
    metadata: dict[str, object]


def _estimate_radius(points: np.ndarray) -> float:
    """Estimate a stable initial neighborhood radius from nearest-neighbor spacing."""
    if len(points) < 2:
        return 1.0
    tree = cKDTree(points)
    distances, _ = tree.query(points, k=2)
    nearest = distances[:, 1]
    median = float(np.median(nearest[np.isfinite(nearest)]))
    return max(median * 3.0, 1.0)


def _sample_points(points: np.ndarray, sample_count: int, seed: int) -> np.ndarray:
    """Deterministically sample input points."""
    if len(points) <= sample_count:
        return points.astype(float, copy=True)
    rng = np.random.default_rng(seed)
    indices = rng.choice(len(points), size=sample_count, replace=False)
    return points[np.sort(indices)].astype(float, copy=True)


def _directionality(points: np.ndarray, tree: cKDTree, radius: float) -> np.ndarray:
    """Compute PCA line-likeness score for each sample point."""
    scores = np.zeros(len(points), dtype=float)
    for idx, point in enumerate(points):
        neighbor_ids = tree.query_ball_point(point, radius)
        if len(neighbor_ids) < 3:
            continue
        local = points[np.asarray(neighbor_ids)] - point
        cov = np.cov(local.T)
        values = np.maximum(np.linalg.eigvalsh(cov), 0.0)
        total = float(np.sum(values))
        if total > 0.0:
            scores[idx] = float(np.max(values) / total)
    return scores


def _contract_once(
    samples: np.ndarray,
    original_points: np.ndarray,
    original_tree: cKDTree,
    radius: float,
    config: L1SkeletonConfig,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Run one L1 attraction plus conditional repulsion iteration."""
    sample_tree = cKDTree(samples)
    confidence = _directionality(samples, sample_tree, radius)
    sigma_min = float(np.min(confidence)) if len(confidence) else 0.0
    sigma_max = float(np.max(confidence)) if len(confidence) else 0.0
    sigma_span = max(sigma_max - sigma_min, 1e-12)
    gaussian = -4.0 / max(radius * radius, 1e-12)

    updated = samples.copy()
    total_move = 0.0
    moved = 0

    for idx, point in enumerate(samples):
        original_ids = original_tree.query_ball_point(point, radius)
        if not original_ids:
            continue
        originals = original_points[np.asarray(original_ids)]
        diffs = point[None, :] - originals
        distances = np.linalg.norm(diffs, axis=1)
        safe_distances = np.maximum(distances, radius * 0.001)
        weights = np.exp((distances * distances) * gaussian) / safe_distances
        attraction = np.average(originals, axis=0, weights=weights)

        repulsion = np.zeros(3, dtype=float)
        repulsion_weight_sum = 0.0
        sample_ids = sample_tree.query_ball_point(point, radius)
        for other_id in sample_ids:
            if other_id == idx:
                continue
            diff = point - samples[int(other_id)]
            distance = float(np.linalg.norm(diff))
            safe_distance = max(distance, radius * 0.001)
            weight = float(np.exp((safe_distance * safe_distance) * gaussian) / safe_distance)
            repulsion += diff * weight
            repulsion_weight_sum += weight

        normalized_sigma = (float(confidence[idx]) - sigma_min) / sigma_span
        mu = config.repulsion_mu_min + normalized_sigma * (config.repulsion_mu - config.repulsion_mu_min)
        new_point = attraction
        if repulsion_weight_sum > 1e-20:
            new_point = new_point + confidence[idx] * mu * repulsion / repulsion_weight_sum

        updated[idx] = new_point
        total_move += float(np.linalg.norm(new_point - point))
        moved += 1

    mean_move = total_move / moved if moved else 0.0
    return updated, confidence, mean_move


def run_l1_skeleton(
    foreground_voxels: np.ndarray,
    *,
    spacing: tuple[float, float, float],
    config: L1SkeletonConfig,
) -> L1RunResult:
    """Run the L1-medial skeleton v1 method on foreground voxel coordinates."""
    original_points = foreground_voxels.astype(float) * np.asarray(spacing, dtype=float)
    samples = _sample_points(original_points, config.sample_count, config.random_seed)
    original_tree = cKDTree(original_points)

    radius = config.initial_radius if config.initial_radius is not None else _estimate_radius(original_points)
    max_radius = config.max_radius
    if max_radius is None:
        extent = np.ptp(original_points, axis=0)
        max_radius = max(radius, float(np.linalg.norm(extent)) * 0.25)

    confidence = np.zeros(len(samples), dtype=float)
    iteration_count = 0
    stage_count = 0
    converged = False
    last_error = 0.0

    while iteration_count < config.max_iterations:
        samples, confidence, last_error = _contract_once(samples, original_points, original_tree, radius, config)
        iteration_count += 1
        if last_error <= config.stop_error:
            stage_count += 1
            next_radius = radius * config.radius_growth
            if next_radius > max_radius or np.isclose(next_radius, radius):
                converged = True
                break
            radius = next_radius

    if iteration_count >= config.max_iterations and last_error <= config.stop_error:
        converged = True

    voxel_samples = samples / np.asarray(spacing, dtype=float)
    metadata = {
        "input_foreground_voxels": int(len(foreground_voxels)),
        "sample_count": int(len(samples)),
        "iterations": int(iteration_count),
        "radius_stages": int(stage_count),
        "final_radius": float(radius),
        "last_movement_error": float(last_error),
        "converged": bool(converged),
        "hit_iteration_cap": bool(iteration_count >= config.max_iterations and not converged),
        "output_points": int(len(voxel_samples)),
        "implementation": "Python-native L1-medial skeleton core v1",
        "deferred_features": ["density weighting", "ellipse re-centering", "reference branch search"],
    }
    return L1RunResult(points=voxel_samples, metadata=metadata)
