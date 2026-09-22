"""Shared histogram styling and collision-aware tick placement."""
from __future__ import annotations

from collections.abc import Mapping

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator


def _tick_boxes_overlap(labels, renderer, *, axis: str) -> bool:
    boxes = [label.get_window_extent(renderer).expanded(1.05, 1.08)
             for label in labels if label.get_visible() and label.get_text()]
    coordinate = (lambda box: box.x0) if axis == "x" else (lambda box: box.y0)
    boxes.sort(key=coordinate)
    return any(first.overlaps(second) for first, second in zip(boxes, boxes[1:]))


def fit_histogram_ticks(axes: Axes, figure: Figure, keys: list[int]) -> None:
    """Thin integer ticks until adjacent rendered labels no longer collide."""
    if not keys:
        return
    canvas = figure.canvas
    figure.tight_layout(pad=1.5)
    canvas.draw()
    axes_width = max(1, axes.bbox.width)
    stride = max(1, -(-len(keys) // max(2, int(axes_width // 38))))
    while True:
        visible = keys[::stride]
        if keys[-1] not in visible:
            visible.append(keys[-1])
        axes.set_xticks(visible)
        canvas.draw()
        renderer = canvas.get_renderer()
        if not _tick_boxes_overlap(axes.get_xticklabels(), renderer, axis="x"):
            break
        if stride >= len(keys):
            axes.set_xticks([keys[0]])
            break
        stride += 1
    for count in range(6, 1, -1):
        axes.yaxis.set_major_locator(MaxNLocator(nbins=count, integer=True, min_n_ticks=2))
        canvas.draw()
        if not _tick_boxes_overlap(axes.get_yticklabels(), canvas.get_renderer(), axis="y"):
            break
    figure.tight_layout(pad=1.5)
    canvas.draw()


def draw_histogram(
    axes: Axes,
    figure: Figure,
    values: Mapping[int, int],
    *,
    title: str,
    xlabel: str,
    ylabel: str,
) -> None:
    """Draw one integer-bin histogram with readable axes at the current size."""
    axes.clear()
    axes.set_title(title, loc="left", fontweight="semibold", color="#193642", pad=11)
    if not values:
        axes.text(0.5, 0.5, "Run TopoStats to view chart", ha="center", va="center",
                  transform=axes.transAxes, color="#718496")
        axes.set_axis_off()
        figure.tight_layout(pad=1.5)
        figure.canvas.draw()
        return
    keys = sorted(values)
    axes.bar(keys, [values[key] for key in keys], width=0.72, color="#198c8e")
    padding = 2 if len(keys) == 1 else max(1, (keys[-1] - keys[0]) * 0.03)
    axes.set_xlim(keys[0] - padding, keys[-1] + padding)
    axes.set_xlabel(xlabel)
    axes.set_ylabel(ylabel)
    axes.set_axisbelow(True)
    axes.grid(axis="y", color="#e0eaed", linewidth=0.8)
    axes.spines[["top", "right"]].set_visible(False)
    axes.tick_params(axis="both", labelcolor="#445f6d", labelsize=9)
    fit_histogram_ticks(axes, figure, keys)
