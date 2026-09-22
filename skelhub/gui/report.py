"""Explicit TopoStats report export."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile
from typing import Callable

from .topology import TopologyResult
from .charting import draw_histogram


def report_paths(destination: str | Path) -> list[Path]:
    root = Path(destination).expanduser()
    return [root / name for name in (
        "summary.json", "node_degree.csv", "cycle_vertices.csv",
        "node_degree.png", "cycle_vertices.png",
    )]


def export_report(
    result: TopologyResult,
    destination: str | Path,
    *,
    overwrite: bool = False,
    progress: Callable[[int | None, str], None] | None = None,
) -> list[Path]:
    """Write the report only after an explicit export request."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    root = Path(destination).expanduser()
    if root.exists() and not root.is_dir():
        raise NotADirectoryError(root)
    targets = report_paths(root)
    existing = [path for path in targets if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Report files already exist: {', '.join(map(str, existing))}")
    root.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(10, f"Preparing five report files in {root}")
    staged: list[tuple[Path, Path]] = []
    try:
        for target in targets:
            with tempfile.NamedTemporaryFile(dir=root, prefix=f".{target.stem}-", suffix=target.suffix, delete=False) as handle:
                staged.append((Path(handle.name), target))
        by_name = {target.name: temp for temp, target in staged}
        by_name["summary.json"].write_text(json.dumps(result.as_report(), indent=2) + "\n")
        if progress:
            progress(28, "JSON summary prepared")
        for name, header, values in (
            ("node_degree.csv", ("degree", "nodes"), result.degree_distribution),
            ("cycle_vertices.csv", ("vertices", "cycles"), result.cycle_vertices_distribution),
        ):
            with by_name[name].open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(sorted(values.items()))
            if progress:
                progress(46 if name == "node_degree.csv" else 62, f"CSV table prepared: {name}")
        for name, title, xlabel, ylabel, values in (
            ("node_degree.png", "Node degree distribution", "Degree", "Nodes", result.degree_distribution),
            ("cycle_vertices.png", "Vertices per cycle — minimum cycle basis", "Vertices", "Cycles", result.cycle_vertices_distribution),
        ):
            figure = Figure(figsize=(7, 4), dpi=150)
            FigureCanvasAgg(figure)
            axes = figure.subplots()
            draw_histogram(axes, figure, values, title=title, xlabel=xlabel, ylabel=ylabel)
            figure.savefig(by_name[name], format="png")
            if progress:
                progress(76 if name == "node_degree.png" else 90, f"PNG chart rendered: {name}")
        for temp, target in staged:
            os.replace(temp, target)
        if progress:
            progress(95, "Report files published to the selected directory")
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
    return targets
