"""Scalar-to-colour mapping and legend data for heatmap views.

Pure data: no Qt or VTK. Two schemes are supported:

- ``bands``: values are grouped into equal-width ranges between the minimum
  and maximum sample; each range gets one colour.
- ``continuous``: each value gets its own colour along the gradient.

Both schemes normally span the sample minimum to maximum. A fixed
``value_range`` (for example 0–1 for a ratio) spans that range instead, so
colours stay comparable between results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


HeatScheme = Literal["bands", "continuous"]
COLOR_PRESETS: dict[str, str] = {
    "Viridis": "viridis",
    "Plasma": "plasma",
    "Inferno": "inferno",
    "Cividis": "cividis",
}
DEFAULT_PRESET = "Viridis"
BAND_COUNT_RANGE = (2, 16)
DEFAULT_BAND_COUNT = 6
GRADIENT_SAMPLES = 256


@dataclass(slots=True, frozen=True)
class HeatLegend:
    """What a colour legend needs to draw one mapping.

    For ``bands``, ``boundaries`` has one more entry than ``colors`` and band
    ``i`` covers ``[boundaries[i], boundaries[i + 1]]``. For ``continuous``,
    ``colors`` samples the gradient from ``vmin`` (first) to ``vmax`` (last).
    When every sample is equal, ``constant`` is True and one colour is used.
    """

    scheme: HeatScheme
    preset: str
    vmin: float
    vmax: float
    colors: np.ndarray
    boundaries: np.ndarray
    title: str
    constant: bool


def _colormap(preset: str):
    if preset not in COLOR_PRESETS:
        raise ValueError(f"Unknown color preset '{preset}'. Choose one of: {', '.join(COLOR_PRESETS)}.")
    from matplotlib import colormaps

    return colormaps[COLOR_PRESETS[preset]]


def _to_rgb8(rgba: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(np.asarray(rgba)[..., :3] * 255.0), 0, 255).astype(np.uint8)


ValueRange = tuple[float, float]


def _value_range(values: np.ndarray, fixed: ValueRange | None = None) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        raise ValueError("Cannot build a heatmap from zero samples.")
    if not np.isfinite(values).all():
        raise ValueError("Heatmap samples must be finite.")
    if fixed is None:
        return float(values.min()), float(values.max())
    low, high = (float(value) for value in fixed)
    if not (np.isfinite(low) and np.isfinite(high) and low < high):
        raise ValueError(f"A fixed colour range needs finite bounds with low < high; got {fixed}.")
    return low, high


def _positions(values: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    """Fraction of the way from vmin to vmax; values outside a fixed range sit at its ends."""
    return np.clip((np.asarray(values, dtype=float) - vmin) / (vmax - vmin), 0.0, 1.0)


def band_indices(values: np.ndarray, band_count: int, value_range: ValueRange | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Assign each value to one of ``band_count`` equal-width ranges.

    Returns ``(indices, boundaries)``. The maximum value falls in the last band.
    Without ``value_range``, constant samples produce one band whose two
    boundaries are equal; with it, the bands always cover that range.
    """
    low, high = BAND_COUNT_RANGE
    if not low <= int(band_count) <= high:
        raise ValueError(f"Color band count must be between {low} and {high}; got {band_count}.")
    vmin, vmax = _value_range(values, value_range)
    values = np.asarray(values, dtype=float)
    if vmax == vmin:
        return np.zeros(values.shape[0], dtype=int), np.asarray([vmin, vmax])
    boundaries = np.linspace(vmin, vmax, int(band_count) + 1)
    indices = np.clip((_positions(values, vmin, vmax) * band_count).astype(int), 0, band_count - 1)
    return indices, boundaries


def discrete_band_colors(
    values: np.ndarray, preset: str, band_count: int, *, title: str = "", value_range: ValueRange | None = None,
) -> tuple[np.ndarray, HeatLegend]:
    """Colour values by equal-width band; returns ``(rgb_uint8[N, 3], legend)``."""
    cmap = _colormap(preset)
    indices, boundaries = band_indices(values, band_count, value_range)
    bands = len(boundaries) - 1
    constant = bands == 1 and boundaries[0] == boundaries[-1]
    positions = np.asarray([0.5]) if constant else (np.arange(bands) + 0.5) / bands
    band_rgb = _to_rgb8(cmap(positions))
    legend = HeatLegend("bands", preset, float(boundaries[0]), float(boundaries[-1]), band_rgb, boundaries, title, constant)
    return band_rgb[indices], legend


def continuous_colors(
    values: np.ndarray, preset: str, *, title: str = "", value_range: ValueRange | None = None,
) -> tuple[np.ndarray, HeatLegend]:
    """Colour values along a continuous gradient; returns ``(rgb_uint8[N, 3], legend)``."""
    cmap = _colormap(preset)
    vmin, vmax = _value_range(values, value_range)
    constant = vmax == vmin
    values = np.asarray(values, dtype=float)
    positions = np.full(values.shape[0], 0.5) if constant else _positions(values, vmin, vmax)
    gradient = _to_rgb8(cmap(np.asarray([0.5]) if constant else np.linspace(0.0, 1.0, GRADIENT_SAMPLES)))
    legend = HeatLegend("continuous", preset, vmin, vmax, gradient, np.asarray([vmin, vmax]), title, constant)
    return _to_rgb8(cmap(positions)), legend


def heat_colors(
    values: np.ndarray,
    scheme: HeatScheme,
    preset: str,
    *,
    band_count: int = DEFAULT_BAND_COUNT,
    title: str = "",
    value_range: ValueRange | None = None,
) -> tuple[np.ndarray, HeatLegend]:
    """Dispatch to banded or continuous colouring, over the data range or a fixed ``value_range``."""
    if scheme == "bands":
        return discrete_band_colors(values, preset, band_count, title=title, value_range=value_range)
    if scheme == "continuous":
        return continuous_colors(values, preset, title=title, value_range=value_range)
    raise ValueError(f"Unknown heatmap scheme '{scheme}'.")


def format_value(value: float) -> str:
    """Compact numeric label with four significant digits."""
    return f"{float(value):.4g}"
