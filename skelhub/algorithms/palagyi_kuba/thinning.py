"""Palagyi-Kuba-style 3D parallel thinning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from scipy import ndimage as ndi

from .config import PalagyiKubaConfig
from .directions import DIRECTION_OFFSETS, SUBITERATION_ORDER, target_transform
from .templates import Template3D, templates_for_mode


@dataclass(slots=True)
class ThinningStats:
    """Runtime metadata from one thinning run."""

    cycle_count: int = 0
    reached_max_cycles: bool = False
    per_direction_deletions: dict[str, list[int]] = field(
        default_factory=lambda: {direction: [] for direction in SUBITERATION_ORDER}
    )


def thin(volume: np.ndarray, config: PalagyiKubaConfig, log=None) -> tuple[np.ndarray, ThinningStats]:
    """Run 12-subiteration thinning until no full-cycle deletion occurs."""
    current = np.asarray(volume, dtype=bool).copy()
    stats = ThinningStats()
    templates = templates_for_mode(config.mode)

    while True:
        if config.max_cycles is not None and stats.cycle_count >= config.max_cycles:
            stats.reached_max_cycles = True
            break

        cycle_deleted = 0
        for direction in SUBITERATION_ORDER:
            delete_mask = _subiteration_delete_mask(current, direction, templates, config.mode)
            deleted = int(np.count_nonzero(delete_mask))
            stats.per_direction_deletions[direction].append(deleted)
            if deleted:
                current[delete_mask] = False
                cycle_deleted += deleted

        stats.cycle_count += 1
        if log:
            log(f"palagyi_kuba cycle {stats.cycle_count}: deleted {cycle_deleted} voxels")
        if cycle_deleted == 0:
            break

    return current.astype(np.uint8, copy=False), stats


def is_curve_endpoint(block: np.ndarray) -> bool:
    """Return True when center is a curve endpoint in its 26-neighborhood."""
    if not block[1, 1, 1]:
        return False
    return int(np.count_nonzero(block)) - 1 == 1


def _is_curve_terminal_or_line_point(block: np.ndarray) -> bool:
    """Preserve curve endpoints, line interiors, and thin curve junctions."""
    if not block[1, 1, 1]:
        return False
    neighbor_count = int(np.count_nonzero(block)) - 1
    if neighbor_count <= 2:
        return True
    six_neighbor_count = sum(
        bool(block[index])
        for index in (
            (0, 1, 1),
            (2, 1, 1),
            (1, 0, 1),
            (1, 2, 1),
            (1, 1, 0),
            (1, 1, 2),
        )
    )
    return neighbor_count <= 6 and six_neighbor_count >= 3


def is_surface_endpoint(block: np.ndarray) -> bool:
    """Return True when center has an opposite white pair in its 6-neighborhood."""
    if not block[1, 1, 1]:
        return False
    opposite_pairs = (
        ((0, 1, 1), (2, 1, 1)),
        ((1, 0, 1), (1, 2, 1)),
        ((1, 1, 0), (1, 1, 2)),
    )
    return any(not block[a] and not block[b] for a, b in opposite_pairs)


def _subiteration_delete_mask(
    volume: np.ndarray,
    direction: str,
    templates: Iterable[Template3D],
    mode: str,
) -> np.ndarray:
    padded = np.pad(volume, 1, mode="constant", constant_values=False)
    delete_mask = np.zeros_like(volume, dtype=bool)
    transform = target_transform(direction)
    candidate_coords = np.argwhere(volume)

    for i, j, k in candidate_coords:
        pi, pj, pk = int(i) + 1, int(j) + 1, int(k) + 1
        block = padded[pi - 1 : pi + 2, pj - 1 : pj + 2, pk - 1 : pk + 2]
        if not _is_directional_border(block, direction):
            continue
        if mode == "curve" and _is_curve_terminal_or_line_point(block):
            continue
        if mode == "surface" and is_surface_endpoint(block):
            continue
        if not _matches_any_template(block, templates, transform):
            continue
        if not _is_simple_point(block):
            continue
        delete_mask[i, j, k] = True

    return _filter_preserving_global_connectivity(volume, delete_mask)


def _is_directional_border(block: np.ndarray, direction: str) -> bool:
    for char in direction:
        offset = DIRECTION_OFFSETS[char]
        if not block[1 + offset[0], 1 + offset[1], 1 + offset[2]]:
            return True
    return False


def _matches_any_template(
    block: np.ndarray,
    templates: Iterable[Template3D],
    transform: dict[tuple[int, int, int], tuple[int, int, int]],
) -> bool:
    return any(_matches_template(block, template, transform) for template in templates)


def _matches_template(
    block: np.ndarray,
    template: Template3D,
    transform: dict[tuple[int, int, int], tuple[int, int, int]],
) -> bool:
    groups: dict[str, list[bool]] = {"x": [], "v": [], "w": [], "y": [], "z": []}
    for a0, layer in enumerate(template.layers):
        for a1, row in enumerate(layer):
            for a2, char in enumerate(row):
                rel = (a0 - 1, a1 - 1, a2 - 1)
                mapped = transform[rel]
                value = bool(block[1 + mapped[0], 1 + mapped[1], 1 + mapped[2]])
                if char == ".":
                    continue
                if char == "B" and not value:
                    return False
                if char == "O" and value:
                    return False
                if char in groups:
                    groups[char].append(value)

    if groups["x"] and not any(groups["x"]):
        return False
    for label in ("v", "w", "y"):
        if groups[label] and all(groups[label]):
            return False
    if groups["z"]:
        if len(groups["z"]) != 2 or groups["z"][0] == groups["z"][1]:
            return False
    return True


def _is_simple_point(block: np.ndarray) -> bool:
    """Conservative local simple-point test using 26/6 topology."""
    if not block[1, 1, 1]:
        return False

    after_fg = block.copy()
    after_fg[1, 1, 1] = False
    if np.count_nonzero(after_fg) == 0:
        return False
    if _component_count(after_fg, connectivity=26) != 1:
        return False

    before_bg = ~block
    after_bg = before_bg.copy()
    after_bg[1, 1, 1] = True
    return _component_count(before_bg, connectivity=6) == _component_count(after_bg, connectivity=6)


def _component_count(values: np.ndarray, *, connectivity: int) -> int:
    if connectivity == 6:
        structure = ndi.generate_binary_structure(3, 1)
    elif connectivity == 26:
        structure = ndi.generate_binary_structure(3, 3)
    else:
        raise ValueError("connectivity must be 6 or 26")
    _, count = ndi.label(values, structure=structure)
    return int(count)


def _filter_preserving_global_connectivity(volume: np.ndarray, delete_mask: np.ndarray) -> np.ndarray:
    """Keep only marked deletions that preserve global 26-connected components."""
    if not np.any(delete_mask):
        return delete_mask

    accepted = np.zeros_like(delete_mask, dtype=bool)
    working = volume.copy()
    baseline = _component_count(working, connectivity=26)
    for i, j, k in np.argwhere(delete_mask):
        if np.count_nonzero(working) <= baseline:
            break
        trial = working.copy()
        trial[int(i), int(j), int(k)] = False
        if _component_count(trial, connectivity=26) == baseline:
            working = trial
            accepted[int(i), int(j), int(k)] = True
    return accepted
