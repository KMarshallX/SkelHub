"""Core Python implementation of the L1-medial skeleton v2 flow."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

from .config import L1SkeletonConfig


MOVING = 0
FIXED = 1
BRANCHED = 2
VIRTUAL = 3
IGNORED = 4


@dataclass(slots=True)
class Branch:
    """Internal branch curve extracted from contracted L1 samples."""

    points: np.ndarray
    virtual_head: bool = False
    virtual_tail: bool = False


@dataclass(slots=True)
class L1RunResult:
    """Internal L1 skeletonization result."""

    points: np.ndarray
    branches: list[Branch]
    metadata: dict[str, object]


def _estimate_radius(points: np.ndarray) -> float:
    """Estimate a stable initial neighborhood radius from nearest-neighbor spacing."""
    if len(points) < 2:
        return 1.0
    tree = cKDTree(points)
    distances, _ = tree.query(points, k=2)
    nearest = distances[:, 1]
    finite = nearest[np.isfinite(nearest)]
    if len(finite) == 0:
        return 1.0
    return max(float(np.median(finite)) * 3.0, 1.0)


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


def _smoothed_confidence(points: np.ndarray, confidence: np.ndarray, knn: int) -> np.ndarray:
    """Smooth directionality over sample neighbors, mirroring the original confidence pass."""
    if len(points) <= 2:
        return confidence.copy()
    k = min(max(knn, 1) + 1, len(points))
    tree = cKDTree(points)
    _, indices = tree.query(points, k=k)
    inverse = 1.0 - confidence
    smoothed = np.zeros_like(confidence)
    for idx, row in enumerate(np.atleast_2d(indices)):
        vals = inverse[np.asarray(row, dtype=int)]
        smoothed[idx] = 1.0 - float(np.mean(vals))
    smoothed[smoothed < 0.0] = 0.5
    return smoothed


def _original_density_weights(original_points: np.ndarray, radius: float) -> np.ndarray:
    """Return inverse local density weights for original points."""
    if len(original_points) == 0:
        return np.zeros(0, dtype=float)
    tree = cKDTree(original_points)
    gaussian = -4.0 / max(radius * radius, 1e-12)
    weights = np.ones(len(original_points), dtype=float)
    for idx, point in enumerate(original_points):
        neighbor_ids = tree.query_ball_point(point, radius)
        density = 1.0
        if neighbor_ids:
            local = original_points[np.asarray(neighbor_ids)] - point
            dist2 = np.einsum("ij,ij->i", local, local)
            density += float(np.sum(np.exp(dist2 * gaussian)))
        weights[idx] = 1.0 / max(density, 1e-12)
    return weights


def _contract_once(
    samples: np.ndarray,
    original_points: np.ndarray,
    original_tree: cKDTree,
    original_density: np.ndarray | None,
    radius: float,
    config: L1SkeletonConfig,
    statuses: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Run one density-aware L1 attraction plus conditional repulsion iteration."""
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
        if statuses[idx] in {BRANCHED, IGNORED}:
            continue
        original_ids = original_tree.query_ball_point(point, radius)
        if not original_ids:
            continue
        original_index = np.asarray(original_ids, dtype=int)
        originals = original_points[original_index]
        diffs = point[None, :] - originals
        distances = np.linalg.norm(diffs, axis=1)
        safe_distances = np.maximum(distances, radius * 0.001)
        weights = np.exp((distances * distances) * gaussian) / safe_distances
        if config.use_density_weighting and original_density is not None:
            weights = weights * original_density[original_index]
        attraction = np.average(originals, axis=0, weights=weights)

        repulsion = np.zeros(3, dtype=float)
        repulsion_weight_sum = 0.0
        sample_ids = sample_tree.query_ball_point(point, radius)
        for other_id in sample_ids:
            if other_id == idx or statuses[int(other_id)] == IGNORED:
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


def _angle_degrees(a: np.ndarray, b: np.ndarray) -> float:
    """Return the smaller angle between two vectors in degrees."""
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 1e-12 or nb <= 1e-12:
        return 180.0
    cos = float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def _search_branch_direction(
    points: np.ndarray,
    statuses: np.ndarray,
    neighbors: np.ndarray,
    start: int,
    direction: np.ndarray,
    max_angle: float,
) -> list[int]:
    """Greedily follow fixed samples from one seed in one direction."""
    branch = [int(start)]
    visited = {int(start)}
    current = int(start)
    current_direction = direction.copy()
    while True:
        best = -1
        best_score: tuple[float, float] | None = None
        for candidate in np.asarray(neighbors[current], dtype=int):
            if candidate in visited or statuses[candidate] == IGNORED:
                continue
            vector = points[candidate] - points[current]
            if float(np.dot(vector, current_direction)) <= 0.0:
                continue
            angle = _angle_degrees(current_direction, vector)
            if statuses[candidate] != FIXED or angle > max_angle:
                if len(branch) > 1:
                    branch.append(int(candidate))
                return branch
            distance = float(np.linalg.norm(vector))
            score = (angle, distance)
            if best_score is None or score < best_score:
                best = int(candidate)
                best_score = score
        if best < 0:
            return branch
        visited.add(best)
        current_direction = points[best] - points[current]
        current = best
        branch.append(current)


def _extract_branches(
    samples: np.ndarray,
    confidence: np.ndarray,
    radius: float,
    config: L1SkeletonConfig,
) -> tuple[list[Branch], np.ndarray]:
    """Extract branch curves from high-confidence contracted samples."""
    statuses = np.full(len(samples), MOVING, dtype=np.uint8)
    if len(samples) == 0:
        return [], statuses

    smoothed = _smoothed_confidence(samples, confidence, config.branch_search_knn)
    statuses[smoothed >= config.eigen_threshold] = FIXED
    if not np.any(statuses == FIXED):
        keep = max(config.accept_branch_size, min(len(samples), max(2, len(samples) // 5)))
        statuses[np.argsort(smoothed)[-keep:]] = FIXED

    k = min(config.branch_search_knn + 1, len(samples))
    _, neighbors = cKDTree(samples).query(samples, k=k)
    neighbors = np.atleast_2d(neighbors)[:, 1:]

    branches: list[Branch] = []
    while True:
        fixed_ids = np.flatnonzero(statuses == FIXED)
        if len(fixed_ids) == 0:
            break
        seed = int(fixed_ids[np.argmax(smoothed[fixed_ids])])
        seed_neighbors = [int(n) for n in neighbors[seed] if statuses[int(n)] == FIXED]
        if not seed_neighbors:
            statuses[seed] = MOVING
            continue
        first = seed_neighbors[0]
        direction = samples[first] - samples[seed]
        forward = _search_branch_direction(samples, statuses, neighbors, seed, direction, config.branch_search_angle)
        backward = _search_branch_direction(samples, statuses, neighbors, seed, -direction, config.branch_search_angle)
        path = list(reversed(backward[1:])) + forward
        unique_path: list[int] = []
        seen: set[int] = set()
        for idx in path:
            if idx not in seen:
                unique_path.append(idx)
                seen.add(idx)

        rate = max(0, int(radius / max(config.initial_radius or radius, 1e-12)))
        accept_size = config.accept_branch_size + config.add_accept_branch_size * rate
        if len(unique_path) < accept_size:
            statuses[np.asarray(unique_path, dtype=int)] = MOVING
            statuses[seed] = MOVING
            continue

        for idx in unique_path:
            statuses[idx] = BRANCHED
        branches.append(Branch(points=samples[np.asarray(unique_path, dtype=int)].copy()))
        _clean_points_near_branch(samples, statuses, branches[-1], config.clean_near_branch_distance)

    if not branches:
        branches = _fallback_branch_tree(samples, config)
    return branches, statuses


def _clean_points_near_branch(samples: np.ndarray, statuses: np.ndarray, branch: Branch, distance: float) -> None:
    """Mark moving points close to accepted branches as ignored."""
    if distance <= 0.0 or len(branch.points) == 0:
        return
    tree = cKDTree(samples)
    for point in branch.points:
        for idx in tree.query_ball_point(point, distance):
            if statuses[int(idx)] == MOVING:
                statuses[int(idx)] = IGNORED


def _fallback_branch_tree(samples: np.ndarray, config: L1SkeletonConfig) -> list[Branch]:
    """Build a deterministic nearest-neighbor branch when confidence search is sparse."""
    if len(samples) == 0:
        return []
    if len(samples) == 1:
        return [Branch(points=samples.copy())]
    direction = _principal_direction(samples)
    ordered = samples[np.argsort(samples @ direction)]
    return [Branch(points=_segment_curve(ordered, config.curve_segment_length))]


def _principal_direction(points: np.ndarray) -> np.ndarray:
    """Return the main PCA direction of a point set."""
    if len(points) < 2:
        return np.array([1.0, 0.0, 0.0], dtype=float)
    centered = points - np.mean(points, axis=0)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    return vh[0]


def _merge_near_branch_ends(branches: list[Branch], distance: float) -> int:
    """Snap clusters of nearby branch endpoints to their average position."""
    if distance <= 0.0 or not branches:
        return 0
    endpoints: list[tuple[int, int, np.ndarray]] = []
    for branch_id, branch in enumerate(branches):
        if len(branch.points) == 0:
            continue
        endpoints.append((branch_id, 0, branch.points[0]))
        endpoints.append((branch_id, len(branch.points) - 1, branch.points[-1]))

    used: set[int] = set()
    merged = 0
    for idx, (_, _, point) in enumerate(endpoints):
        if idx in used:
            continue
        group = [idx]
        for other_idx in range(idx + 1, len(endpoints)):
            if other_idx in used:
                continue
            if float(np.linalg.norm(endpoints[other_idx][2] - point)) <= distance:
                group.append(other_idx)
        if len(group) < 2:
            continue
        target = np.mean([endpoints[item][2] for item in group], axis=0)
        for item in group:
            branch_id, node_id, _ = endpoints[item]
            branches[branch_id].points[node_id] = target
            used.add(item)
        merged += 1
    return merged


def _smooth_curve(points: np.ndarray, angle_threshold: float, max_time: int = 3) -> np.ndarray:
    """Smooth high-angle internal nodes."""
    if len(points) < 3:
        return points
    smoothed = points.copy()
    for _ in range(max_time):
        changed = False
        next_points = smoothed.copy()
        for idx in range(1, len(smoothed) - 1):
            angle = _angle_degrees(smoothed[idx] - smoothed[idx - 1], smoothed[idx + 1] - smoothed[idx])
            if angle > angle_threshold:
                next_points[idx] = 0.5 * smoothed[idx] + 0.25 * smoothed[idx - 1] + 0.25 * smoothed[idx + 1]
                changed = True
        smoothed = next_points
        if not changed:
            break
    return smoothed


def _segment_curve(points: np.ndarray, segment_length: float) -> np.ndarray:
    """Down-sample a branch curve by arc-length spacing."""
    if len(points) <= 2:
        return points
    kept = [points[0]]
    last = points[0]
    for point in points[1:-1]:
        if float(np.linalg.norm(point - last)) >= segment_length:
            kept.append(point)
            last = point
    if float(np.linalg.norm(points[-1] - kept[-1])) > 1e-12:
        kept.append(points[-1])
    return np.asarray(kept, dtype=float)


def _final_segment_branches(branches: list[Branch], config: L1SkeletonConfig) -> tuple[list[Branch], bool]:
    """Apply final smoothing and segmentation to every branch."""
    segmented: list[Branch] = []
    changed = False
    for branch in branches:
        curve = _smooth_curve(branch.points, config.branch_search_angle / 1.5, max_time=3)
        curve = _segment_curve(curve, config.curve_segment_length)
        changed = changed or len(curve) != len(branch.points)
        segmented.append(Branch(points=curve, virtual_head=branch.virtual_head, virtual_tail=branch.virtual_tail))
    return segmented, changed


def _plane_basis(tangent: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return normalized tangent and two orthonormal cross-section axes."""
    normal = tangent.astype(float, copy=True)
    norm = float(np.linalg.norm(normal))
    if norm <= 1e-12:
        normal = np.array([1.0, 0.0, 0.0], dtype=float)
    else:
        normal /= norm
    helper = np.array([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(helper, normal))) > 0.9:
        helper = np.array([0.0, 1.0, 0.0], dtype=float)
    axis_u = np.cross(normal, helper)
    axis_u /= max(float(np.linalg.norm(axis_u)), 1e-12)
    axis_v = np.cross(normal, axis_u)
    axis_v /= max(float(np.linalg.norm(axis_v)), 1e-12)
    return normal, axis_u, axis_v


def _fit_ellipse_center(points_2d: np.ndarray) -> np.ndarray | None:
    """Fit a 2D ellipse center with nonlinear least squares."""
    if len(points_2d) < 6:
        return None
    center0 = np.mean(points_2d, axis=0)
    spread = np.std(points_2d, axis=0)
    params0 = np.array([center0[0], center0[1], max(spread[0], 1e-3), max(spread[1], 1e-3), 0.0])

    def residual(params: np.ndarray) -> np.ndarray:
        cx, cy, a_raw, b_raw, phi = params
        a = max(abs(float(a_raw)), 1e-6)
        b = max(abs(float(b_raw)), 1e-6)
        shifted = points_2d - np.array([cx, cy])
        cos_p = np.cos(phi)
        sin_p = np.sin(phi)
        x = cos_p * shifted[:, 0] + sin_p * shifted[:, 1]
        y = -sin_p * shifted[:, 0] + cos_p * shifted[:, 1]
        return np.sqrt((x / a) ** 2 + (y / b) ** 2) - 1.0

    result = least_squares(residual, params0, max_nfev=80)
    if not result.success:
        return None
    return np.asarray(result.x[:2], dtype=float)


def _recenter_branches(
    branches: list[Branch],
    original_points: np.ndarray,
    radius: float,
) -> tuple[list[Branch], int, int]:
    """Re-center branch nodes by fitting ellipse centers in local cross-section planes."""
    if not branches or len(original_points) < 6:
        return branches, 0, 0
    tree = cKDTree(original_points)
    recentered: list[Branch] = []
    attempted = 0
    applied = 0
    plane_half_width = max(radius * 0.35, 1e-6)
    query_radius = max(radius, plane_half_width * 2.0)

    for branch in branches:
        points = branch.points.copy()
        if len(points) < 3:
            recentered.append(branch)
            continue
        updated = points.copy()
        for idx, point in enumerate(points):
            if idx == 0:
                tangent = points[1] - points[0]
            elif idx == len(points) - 1:
                tangent = points[-1] - points[-2]
            else:
                tangent = points[idx + 1] - points[idx - 1]
            normal, axis_u, axis_v = _plane_basis(tangent)
            nearby_ids = tree.query_ball_point(point, query_radius)
            if len(nearby_ids) < 6:
                continue
            nearby = original_points[np.asarray(nearby_ids, dtype=int)]
            rel = nearby - point
            plane_distance = rel @ normal
            cross = rel[np.abs(plane_distance) <= plane_half_width]
            if len(cross) < 6:
                continue
            projected = np.column_stack((cross @ axis_u, cross @ axis_v))
            attempted += 1
            center = _fit_ellipse_center(projected)
            if center is None or not np.all(np.isfinite(center)):
                continue
            updated[idx] = point + center[0] * axis_u + center[1] * axis_v
            applied += 1
        updated = _smooth_curve(updated, angle_threshold=45.0, max_time=2)
        recentered.append(Branch(points=updated, virtual_head=branch.virtual_head, virtual_tail=branch.virtual_tail))
    return recentered, attempted, applied


def run_l1_skeleton(
    foreground_voxels: np.ndarray,
    *,
    spacing: tuple[float, float, float],
    config: L1SkeletonConfig,
) -> L1RunResult:
    """Run the L1-medial skeleton v2 method on foreground voxel coordinates."""
    original_points = foreground_voxels.astype(float) * np.asarray(spacing, dtype=float)
    samples = _sample_points(original_points, config.sample_count, config.random_seed)
    original_tree = cKDTree(original_points)

    radius = config.initial_radius if config.initial_radius is not None else _estimate_radius(original_points)
    initial_radius = radius
    max_radius = config.max_radius
    if max_radius is None:
        extent = np.ptp(original_points, axis=0)
        max_radius = max(radius, float(np.linalg.norm(extent)) * 0.25)

    statuses = np.full(len(samples), MOVING, dtype=np.uint8)
    confidence = np.zeros(len(samples), dtype=float)
    branches: list[Branch] = []
    iteration_count = 0
    stage_count = 0
    merged_endpoint_groups = 0
    converged = False
    last_error = 0.0

    while iteration_count < config.max_iterations:
        density = _original_density_weights(original_points, radius) if config.use_density_weighting else None
        samples, confidence, last_error = _contract_once(
            samples,
            original_points,
            original_tree,
            density,
            radius,
            config,
            statuses,
        )
        iteration_count += 1
        if last_error <= config.stop_error:
            stage_count += 1
            stage_branches, statuses = _extract_branches(samples, confidence, radius, config)
            if stage_branches:
                branches = stage_branches
                merged_endpoint_groups += _merge_near_branch_ends(branches, config.branch_merge_distance)
            next_radius = radius * config.radius_growth
            if next_radius > max_radius or np.isclose(next_radius, radius):
                converged = True
                break
            radius = next_radius

    if not branches:
        branches, statuses = _extract_branches(samples, confidence, radius, config)
    if not branches:
        branches = _fallback_branch_tree(samples, config)

    segmented = False
    if config.output_mode == "branches":
        branches, segmented = _final_segment_branches(branches, config)

    recenter_attempted = 0
    recenter_applied = 0
    if config.output_mode == "branches" and config.use_recentering:
        branches, recenter_attempted, recenter_applied = _recenter_branches(branches, original_points, radius)

    if iteration_count >= config.max_iterations and last_error <= config.stop_error:
        converged = True

    spacing_array = np.asarray(spacing, dtype=float)
    voxel_samples = samples / spacing_array
    voxel_branches = [
        Branch(points=branch.points / spacing_array, virtual_head=branch.virtual_head, virtual_tail=branch.virtual_tail)
        for branch in branches
    ]
    branch_points = int(sum(len(branch.points) for branch in voxel_branches))
    metadata = {
        "input_foreground_voxels": int(len(foreground_voxels)),
        "sample_count": int(len(samples)),
        "iterations": int(iteration_count),
        "radius_stages": int(stage_count),
        "initial_radius": float(initial_radius),
        "final_radius": float(radius),
        "last_movement_error": float(last_error),
        "converged": bool(converged),
        "hit_iteration_cap": bool(iteration_count >= config.max_iterations and not converged),
        "output_points": int(len(voxel_samples)),
        "output_mode": config.output_mode,
        "branch_count": int(len(voxel_branches)),
        "branch_points": int(branch_points),
        "density_weighting": bool(config.use_density_weighting),
        "recentering_attempted": int(recenter_attempted),
        "recentering_applied": int(recenter_applied),
        "segmentation_applied": bool(segmented),
        "merged_endpoint_groups": int(merged_endpoint_groups),
        "status_counts": {
            "moving": int(np.count_nonzero(statuses == MOVING)),
            "fixed": int(np.count_nonzero(statuses == FIXED)),
            "branched": int(np.count_nonzero(statuses == BRANCHED)),
            "virtual": int(np.count_nonzero(statuses == VIRTUAL)),
            "ignored": int(np.count_nonzero(statuses == IGNORED)),
        },
        "implementation": "Python-native L1-medial skeleton v2",
    }
    return L1RunResult(points=voxel_samples, branches=voxel_branches, metadata=metadata)
