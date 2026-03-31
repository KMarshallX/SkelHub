"""Single-object skeleton extraction loop."""

from __future__ import annotations

import math
import signal
import time
from typing import Callable, Iterable

import numpy as np

from core.dilation import local_scale_adaptive_dilation
from core.distance_transform import compute_fdt
from core.geodesic import compute_geodesic_distance
from core.lsf import compute_lsf
from core.path_cost import minimum_cost_path
from utils.connected_components import label_subtrees
from utils.root_detection import detect_root


_STAGNATION_ARM_SECONDS = 10.0
_STAGNATION_FUSE_SECONDS = 60.0


class _SafetyFuseTriggered(RuntimeError):
    """Raised when prolonged no-progress execution should stop safely."""


def significance(branch_coords: list[tuple], lsf: np.ndarray, marked_mask: np.ndarray) -> float:
    """Return the branch significance outside the already-marked object region."""
    lsf_values = np.asarray(lsf, dtype=np.float32)
    marked = np.asarray(marked_mask, dtype=bool)

    if lsf_values.ndim != 3 or marked.ndim != 3:
        raise ValueError("significance expects 3D inputs.")
    if lsf_values.shape != marked.shape:
        raise ValueError("lsf and marked_mask must have the same shape.")
    if not branch_coords:
        return 0.0

    total = 0.0
    shape = lsf_values.shape
    for coord in branch_coords:
        voxel = tuple(int(value) for value in coord)
        if len(voxel) != 3:
            raise ValueError("branch_coords must contain 3D coordinates.")
        if any(index < 0 or index >= limit for index, limit in zip(voxel, shape, strict=True)):
            raise ValueError("branch_coords contains a coordinate outside the volume bounds.")
        if not marked[voxel]:
            total += float(lsf_values[voxel])

    return total


def _neighbour_coords(coord: tuple[int, int, int], shape: tuple[int, int, int]) -> Iterable[tuple[int, int, int]]:
    """Yield valid 26-neighbour coordinates."""
    z, y, x = coord
    for dz in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dz == 0 and dy == 0 and dx == 0:
                    continue
                nz = z + dz
                ny = y + dy
                nx = x + dx
                if 0 <= nz < shape[0] and 0 <= ny < shape[1] and 0 <= nx < shape[2]:
                    yield (nz, ny, nx)


def _path_graph_metrics(
    accepted_paths: list[list[tuple]],
    lsf: np.ndarray,
    fdt: np.ndarray,
    root: tuple[int, int, int] | None = None,
) -> tuple[int, list[tuple[int, int, int]]]:
    """Count significant branches and endpoints from accepted MCP edges only."""
    adjacency: dict[tuple[int, int, int], set[tuple[int, int, int]]] = {}

    for path in accepted_paths:
        normalised_path = [tuple(int(value) for value in coord) for coord in path]
        if len(normalised_path) == 1:
            adjacency.setdefault(normalised_path[0], set())
            continue
        for start, end in zip(normalised_path, normalised_path[1:]):
            adjacency.setdefault(start, set()).add(end)
            adjacency.setdefault(end, set()).add(start)

    if root is not None:
        adjacency.setdefault(tuple(int(value) for value in root), set())
    if not adjacency:
        return 0, []

    nodes = {coord for coord, neighbours in adjacency.items() if len(neighbours) != 2}
    if len(adjacency) == 1:
        return 0, []
    if not nodes:
        return 1, []

    visited_edges: set[frozenset[tuple[int, int, int]]] = set()
    significant_branches = 0
    significant_endpoints: list[tuple[int, int, int]] = []
    for node in nodes:
        for neighbour in adjacency[node]:
            edge = frozenset((node, neighbour))
            if edge in visited_edges:
                continue

            segment = [node, neighbour]
            visited_edges.add(edge)
            prev = node
            cursor = neighbour
            while cursor not in nodes:
                next_candidates = [candidate for candidate in adjacency[cursor] if candidate != prev]
                if not next_candidates:
                    break
                next_coord = next_candidates[0]
                edge = frozenset((cursor, next_coord))
                if edge in visited_edges:
                    break
                visited_edges.add(edge)
                segment.append(next_coord)
                prev, cursor = cursor, next_coord

            start_node = segment[0]
            end_node = segment[-1]
            start_degree = len(adjacency[start_node])
            end_degree = len(adjacency[end_node])

            attachment = None
            endpoint = None
            if start_degree == 1 and end_degree > 1:
                attachment = end_node
                endpoint = start_node
            elif end_degree == 1 and start_degree > 1:
                attachment = start_node
                endpoint = end_node

            if attachment is None:
                if start_degree == 1 and end_degree == 1:
                    significant_branches += 1
                continue

            branch_signal = float(sum(float(lsf[coord]) for coord in segment if coord != attachment))
            threshold = 3.0 + 0.5 * float(fdt[attachment])
            if branch_signal >= threshold:
                significant_branches += 1
                significant_endpoints.append(endpoint)

    significant_endpoints.sort()
    return significant_branches, significant_endpoints


def count_skeletal_branches(skeleton_mask: np.ndarray) -> int:
    """Count graph branches in a voxel skeleton using 26-neighbour connectivity."""
    skeleton = np.asarray(skeleton_mask, dtype=bool)
    if skeleton.ndim != 3:
        raise ValueError("count_skeletal_branches expects a 3D mask.")
    if not np.any(skeleton):
        return 0

    shape = skeleton.shape
    coords = [tuple(int(value) for value in coord) for coord in np.argwhere(skeleton)]
    adjacency: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    for coord in coords:
        neighbours = [nbr for nbr in _neighbour_coords(coord, shape) if skeleton[nbr]]
        adjacency[coord] = neighbours

    nodes = {coord for coord, neighbours in adjacency.items() if len(neighbours) != 2}
    if not nodes:
        return 1

    visited_edges: set[frozenset[tuple[int, int, int]]] = set()
    branches = 0
    for node in nodes:
        for neighbour in adjacency[node]:
            edge = frozenset((node, neighbour))
            if edge in visited_edges:
                continue

            branches += 1
            visited_edges.add(edge)
            prev = node
            cursor = neighbour
            while cursor not in nodes:
                next_candidates = [candidate for candidate in adjacency[cursor] if candidate != prev]
                if not next_candidates:
                    break
                next_coord = next_candidates[0]
                edge = frozenset((cursor, next_coord))
                if edge in visited_edges:
                    break
                visited_edges.add(edge)
                prev, cursor = cursor, next_coord

    return branches


def skeleton_endpoints(skeleton_mask: np.ndarray) -> list[tuple[int, int, int]]:
    """Return degree-1 voxels of the skeleton graph."""
    skeleton = np.asarray(skeleton_mask, dtype=bool)
    if skeleton.ndim != 3:
        raise ValueError("skeleton_endpoints expects a 3D mask.")

    shape = skeleton.shape
    endpoints: list[tuple[int, int, int]] = []
    for coord in np.argwhere(skeleton):
        voxel = tuple(int(value) for value in coord)
        degree = sum(1 for neighbour in _neighbour_coords(voxel, shape) if skeleton[neighbour])
        if degree == 1:
            endpoints.append(voxel)
    endpoints.sort()
    return endpoints


def extract_skeleton(
    volume: np.ndarray,
    root_method: str = "max_fdt",
    threshold_scale: float = 1.0,
    max_iterations: int = 200,
    log: Callable[[str], None] | None = None,
) -> tuple[np.ndarray, dict]:
    """Extract a curve skeleton for one object mask or sub-volume."""
    memberships = np.clip(np.asarray(volume, dtype=np.float32), 0.0, 1.0)
    if memberships.ndim != 3:
        raise ValueError("extract_skeleton expects a 3D volume.")
    if threshold_scale <= 0.0:
        raise ValueError("threshold_scale must be positive.")
    if max_iterations < 0:
        raise ValueError("max_iterations must be non-negative.")

    object_mask = memberships > 0.0
    skeleton = np.zeros_like(object_mask, dtype=bool)
    metadata = {
        "root": None,
        "accepted_paths": [],
        "accepted_branch_paths": 0,
        "branch_count": 0,
        "endpoints": [],
        "iterations": 0,
        "branches_added_per_iteration": [],
        "max_iterations": int(max_iterations),
        "max_iterations_reached": False,
        "geodesic_calls": 0,
        "minimum_cost_path_calls": 0,
        "dilation_calls": 0,
        "iteration_limit_reason": None,
        "safety_fuse_triggered": False,
        "safety_fuse_warning": None,
        "complexity_reference": {"log2_n": 0.0, "sqrt_n": 0.0},
    }
    if not np.any(object_mask):
        return skeleton, metadata

    fdt = compute_fdt(memberships)
    lsf = compute_lsf(memberships, fdt)
    root = detect_root(memberships, object_mask, fdt, method=root_method)
    metadata["root"] = root

    skeleton[root] = True
    marked_mask = local_scale_adaptive_dilation(object_mask, [root], fdt)
    metadata["dilation_calls"] += 1
    fuse_supported = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")
    fuse_stage = "idle"
    previous_signal_handler = None
    warning = (
        "warning: safety fuse triggered after prolonged no-progress state; "
        "iteration did not complete; saving partial skeleton; "
        "output may be incomplete"
    )

    def _cancel_safety_fuse() -> None:
        nonlocal fuse_stage
        if not fuse_supported:
            return
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        fuse_stage = "idle"

    def _arm_safety_fuse() -> None:
        nonlocal fuse_stage
        if not fuse_supported:
            return
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        fuse_stage = "arm"
        signal.setitimer(signal.ITIMER_REAL, _STAGNATION_ARM_SECONDS)

    def _handle_safety_alarm(_signum: int, _frame: object) -> None:
        nonlocal fuse_stage
        if fuse_stage == "arm":
            fuse_stage = "countdown"
            if log is not None:
                log(
                    "warning: no skeleton-growth progress for "
                    f"{_STAGNATION_ARM_SECONDS:.0f}s; arming safety fuse for "
                    f"{_STAGNATION_FUSE_SECONDS:.0f}s"
                )
            signal.setitimer(signal.ITIMER_REAL, _STAGNATION_FUSE_SECONDS)
            return
        raise _SafetyFuseTriggered(warning)

    if fuse_supported:
        previous_signal_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _handle_safety_alarm)
        _arm_safety_fuse()

    if log is not None:
        log(f"root={root}, initial marked voxels={int(np.count_nonzero(marked_mask))}")

    try:
        while True:
            subtrees = label_subtrees(object_mask, marked_mask)
            if not subtrees:
                break
            if metadata["iterations"] >= max_iterations:
                metadata["max_iterations_reached"] = True
                metadata["iteration_limit_reason"] = "maximum iteration cap reached"
                if log is not None:
                    log(
                        "maximum iteration cap reached "
                        f"({max_iterations}); stopping object safely"
                    )
                break

            metadata["iterations"] += 1
            branches_added_this_iteration = 0
            source_coords = [tuple(int(value) for value in coord) for coord in np.argwhere(skeleton)]
            geodesic = compute_geodesic_distance(object_mask, marked_mask)
            metadata["geodesic_calls"] += 1

            found_any = False
            for subtree_label, subtree_mask in subtrees:
                strong_quench = subtree_mask & (lsf > 0.5)
                strong_count = int(np.count_nonzero(strong_quench))
                if strong_count == 0:
                    continue

                candidate_distance = np.where(strong_quench, geodesic, -np.inf)
                if not np.isfinite(candidate_distance).any():
                    continue

                farthest_index = np.unravel_index(int(np.argmax(candidate_distance)), candidate_distance.shape)
                path = minimum_cost_path(
                    object_mask,
                    lsf,
                    source_coords,
                    tuple(int(value) for value in farthest_index),
                )
                metadata["minimum_cost_path_calls"] += 1
                if not path:
                    continue

                branch_significance = significance(path, lsf, marked_mask)
                junction = tuple(int(value) for value in path[-1])
                threshold = threshold_scale * (3.0 + 0.5 * float(fdt[junction]))
                if branch_significance < threshold:
                    if log is not None:
                        log(
                            "subtree "
                            f"{subtree_label}: rejected branch len={len(path)} "
                            f"sig={branch_significance:.3f} threshold={threshold:.3f}"
                        )
                    continue

                for coord in path:
                    skeleton[tuple(int(value) for value in coord)] = True
                dilated = local_scale_adaptive_dilation(object_mask, path, fdt)
                metadata["dilation_calls"] += 1
                marked_mask |= dilated
                metadata["accepted_paths"].append(path)
                metadata["accepted_branch_paths"] = len(metadata["accepted_paths"])
                found_any = True
                branches_added_this_iteration += 1
                _arm_safety_fuse()
                if log is not None:
                    log(
                        "subtree "
                        f"{subtree_label}: accepted branch len={len(path)} "
                        f"strong_quench={strong_count} sig={branch_significance:.3f}"
                    )

            metadata["branches_added_per_iteration"].append(branches_added_this_iteration)
            if not found_any:
                break
    except _SafetyFuseTriggered:
        metadata["safety_fuse_triggered"] = True
        metadata["iteration_limit_reason"] = "safety fuse triggered after prolonged no-progress state"
        metadata["safety_fuse_warning"] = warning
        if log is not None:
            log(warning)
    finally:
        if fuse_supported:
            _cancel_safety_fuse()
            if previous_signal_handler is not None:
                signal.signal(signal.SIGALRM, previous_signal_handler)

    metadata["branch_count"], metadata["endpoints"] = _path_graph_metrics(
        metadata["accepted_paths"],
        lsf,
        fdt,
        root=root,
    )
    terminal_branches = max(int(metadata["branch_count"]), 1)
    metadata["complexity_reference"] = {
        "log2_n": float(math.log2(terminal_branches)),
        "sqrt_n": float(math.sqrt(terminal_branches)),
    }
    if log is not None:
        log(f"final branch_count={metadata['branch_count']}")
    return skeleton, metadata
