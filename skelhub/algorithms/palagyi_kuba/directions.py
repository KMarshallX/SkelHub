"""Directional conventions for the Palagyi-Kuba 12-subiteration schedule."""

from __future__ import annotations

from typing import Final


# NumPy axis convention locked by the implementation plan:
# axis0 = U/D, axis1 = N/S, axis2 = W/E.
DIRECTION_OFFSETS: Final[dict[str, tuple[int, int, int]]] = {
    "U": (-1, 0, 0),
    "D": (1, 0, 0),
    "N": (0, -1, 0),
    "S": (0, 1, 0),
    "W": (0, 0, -1),
    "E": (0, 0, 1),
}

SUBITERATION_ORDER: Final[tuple[str, ...]] = (
    "US",
    "NE",
    "DW",
    "SE",
    "UW",
    "DN",
    "SW",
    "UN",
    "DE",
    "NW",
    "UE",
    "DS",
)

AXIS_MAPPING: Final[dict[str, str]] = {
    "axis0": "U/D",
    "axis1": "N/S",
    "axis2": "W/E",
    "negative": "U/N/W",
    "positive": "D/S/E",
}


def target_transform(direction: str) -> dict[tuple[int, int, int], tuple[int, int, int]]:
    """Map US-template offsets into a target directional subiteration.

    Template tables are encoded in the base US orientation.  A coordinate's
    first component is interpreted along U/D, second along N/S, and third
    along W/E.  The first base direction, U, maps to ``direction[0]`` and the
    second base direction, S, maps to ``direction[1]``.
    """
    if direction not in SUBITERATION_ORDER:
        raise ValueError(f"Unknown Palagyi-Kuba direction: {direction}")

    first = DIRECTION_OFFSETS[direction[0]]
    second = DIRECTION_OFFSETS[direction[1]]
    used_axes = {idx for vector in (first, second) for idx, value in enumerate(vector) if value}
    remaining_axis = ({0, 1, 2} - used_axes).pop()
    remaining = [0, 0, 0]
    remaining[remaining_axis] = -1

    mapping: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for a0 in (-1, 0, 1):
        for a1 in (-1, 0, 1):
            for a2 in (-1, 0, 1):
                mapped = tuple(
                    (-a0 * first[idx]) + (a1 * second[idx]) + (-a2 * remaining[idx])
                    for idx in range(3)
                )
                mapping[(a0, a1, a2)] = mapped
    return mapping
