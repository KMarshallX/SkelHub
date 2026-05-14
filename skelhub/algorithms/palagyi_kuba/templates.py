"""Template tables for Palagyi-Kuba 3D thinning.

The tables are explicit 3x3x3 encodings of the symbols from the local
Palagyi-Kuba reference figures.  Layers are ordered U, middle, D; rows are
N, middle, S; columns are W, middle, E.  The center voxel is written as ``B``
for required foreground.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


LayerTable = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class Template3D:
    """One symbolic Palagyi-Kuba 3x3x3 matching template."""

    label: str
    layers: tuple[LayerTable, LayerTable, LayerTable]


CURVE_TEMPLATE_SOURCE = "PK_templates_figure.png"
SURFACE_TEMPLATE_SOURCE = "PK_surface_templates_figure.png"


def _empty_layers() -> list[list[list[str]]]:
    return [[["." for _ in range(3)] for _ in range(3)] for _ in range(3)]


def _template(
    label: str,
    *,
    white: Iterable[tuple[int, int, int]] = (),
    black: Iterable[tuple[int, int, int]] = (),
    x: Iterable[tuple[int, int, int]] = (),
    v: Iterable[tuple[int, int, int]] = (),
    w: Iterable[tuple[int, int, int]] = (),
    y: Iterable[tuple[int, int, int]] = (),
    z: Iterable[tuple[int, int, int]] = (),
) -> Template3D:
    grid = _empty_layers()
    grid[1][1][1] = "B"
    for coords, char in (
        (white, "O"),
        (black, "B"),
        (x, "x"),
        (v, "v"),
        (w, "w"),
        (y, "y"),
        (z, "z"),
    ):
        for a0, a1, a2 in coords:
            grid[a0 + 1][a1 + 1][a2 + 1] = char
    layers = tuple(tuple("".join(row) for row in layer) for layer in grid)
    return Template3D(label=label, layers=layers)  # type: ignore[arg-type]


# Base US curve templates.  These are kept as explicit tables and intentionally
# overlap with topology checks in thinning.py; the topology checks are the final
# guard against connectivity or hole-changing deletions.
CURVE_TEMPLATES: tuple[Template3D, ...] = (
    _template("T1", white=[(-1, -1, -1), (-1, -1, 0), (-1, -1, 1)], x=[(0, 1, -1), (0, 1, 0), (0, 1, 1)], black=[(1, 0, 0)]),
    _template("T2", white=[(1, -1, -1), (1, -1, 0), (1, -1, 1)], x=[(-1, -1, -1), (-1, -1, 0), (-1, -1, 1), (0, 1, 0)], black=[(1, 0, 0)]),
    _template("T3", white=[(-1, -1, -1), (-1, -1, 0), (-1, -1, 1)], x=[(0, 1, 1)], black=[(0, 0, 1), (1, 0, 0)]),
    _template("T4", v=[(-1, -1, -1), (1, -1, -1)], w=[(-1, 1, 1), (1, 1, 1)], black=[(0, 0, -1), (0, 1, 0), (1, 0, 0)]),
    _template("T5", v=[(-1, -1, -1), (1, -1, -1)], w=[(-1, 1, 1), (1, 1, 1)], z=[(0, -1, 1), (0, 1, -1)], black=[(0, 0, 1), (1, 0, 0)]),
    _template("T6", v=[(-1, 1, -1), (-1, 1, 1)], z=[(0, -1, -1), (1, -1, -1)], black=[(-1, 0, -1), (0, 0, 1), (1, 0, 0)]),
    _template("T7", v=[(-1, 1, -1), (1, 1, -1)], black=[(0, 0, 1), (0, 1, 0), (1, 0, 0)]),
    _template("T8", v=[(-1, 1, 1), (1, 1, 1)], black=[(0, 0, -1), (0, 0, 1), (1, 0, 0)]),
    _template("T9", z=[(-1, -1, -1), (0, 1, -1)], black=[(0, 0, 1), (0, 1, 0), (1, 0, 0)]),
    _template("T10", z=[(-1, -1, 1), (0, 1, 1)], black=[(0, 0, -1), (0, 0, 1), (1, 0, 0)]),
    _template("T11", white=[(-1, -1, -1), (-1, -1, 0), (-1, -1, 1)], black=[(0, 0, 0), (1, 0, 1)]),
    _template("T12", white=[(-1, -1, -1), (-1, -1, 0), (-1, -1, 1)], black=[(0, 0, 0), (1, 0, -1)]),
    _template("T13", white=[(-1, -1, -1), (-1, 0, -1), (-1, 1, -1), (-1, -1, 0), (-1, 1, 0), (-1, -1, 1), (-1, 0, 1), (-1, 1, 1)], black=[(0, 0, 1), (1, 0, 0)]),
    _template("T14", white=[(-1, -1, 0), (-1, -1, 1), (-1, 0, 1), (-1, 1, 1)], black=[(0, 0, -1), (0, 1, 0), (1, 0, 0)]),
)


SURFACE_TEMPLATES: tuple[Template3D, ...] = (
    _template("T1'", white=[(-1, -1, -1), (-1, -1, 0), (-1, -1, 1)], x=[(0, 1, 0)], y=[(0, -1, 0)], black=[(1, 0, 0)]),
    _template("T2'", white=[(1, -1, -1), (1, -1, 0), (1, -1, 1)], x=[(0, 1, 0)], y=[(0, -1, 0)], black=[(1, 0, 0)]),
    _template("T7'", v=[(-1, 1, -1), (1, 1, -1)], black=[(0, 0, 1), (0, 1, 0), (1, 0, 0)]),
    _template("T8'", v=[(-1, 1, 1), (1, 1, 1)], black=[(0, 0, -1), (0, 0, 1), (1, 0, 0)]),
    _template("T9'", z=[(-1, -1, -1), (0, 1, -1)], black=[(0, 0, 1), (0, 1, 0), (1, 0, 0)]),
    _template("T10'", z=[(-1, -1, 1), (0, 1, 1)], black=[(0, 0, -1), (0, 0, 1), (1, 0, 0)]),
)


def templates_for_mode(mode: str) -> tuple[Template3D, ...]:
    """Return the template set for a thinning mode."""
    if mode == "curve":
        return CURVE_TEMPLATES
    if mode == "surface":
        return SURFACE_TEMPLATES
    raise ValueError(f"Unknown Palagyi-Kuba mode: {mode}")
