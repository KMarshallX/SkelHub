"""GUI-facing operations using the same services as the helper scripts."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Callable

from skelhub.postprocessing.checker import check_paths
from skelhub.postprocessing.crop_escaping_graph_patches import main as crop_main
from skelhub.postprocessing.protograph_cleaner import clean_protograph_file


Progress = Callable[[int | None, str], None]


def clean_graph(source: str, destination: str, progress: Progress | None = None) -> str:
    if progress:
        progress(10, f"Reading proto-graph: {Path(source).name}")

    last_bucket = -1
    def node_progress(processed: int, total: int) -> None:
        nonlocal last_bucket
        bucket = int(processed * 20 / total) if total else 20
        if progress and (bucket != last_bucket or processed == total):
            last_bucket = bucket
            progress(20 + int(65 * processed / total) if total else 85,
                     f"Contracting degree-2 nodes: {processed}/{total} input nodes")

    stats = clean_protograph_file(source, destination, overwrite=True, progress=node_progress)
    if progress:
        progress(95, f"Clean GraphML written: {destination}")
    return (f"Nodes: {stats.input_nodes} → {stats.output_nodes}\n"
            f"Edges: {stats.input_edges} → {stats.output_edges}\n"
            f"Removed degree-2 nodes: {stats.removed_nodes}\nOutput: {destination}")


def check_graph(foreground: str, skeleton: str, connectivity: int, progress: Progress | None = None) -> str:
    stream = StringIO()
    with redirect_stdout(stream), redirect_stderr(stream):
        try:
            check_paths(foreground, skeleton, connectivity, progress=progress)
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise ValueError(stream.getvalue().strip() or "Check failed.") from exc
    return stream.getvalue().strip()


def crop_graph(arguments: list[str], progress: Progress | None = None) -> str:
    stream = StringIO()
    with redirect_stdout(stream), redirect_stderr(stream):
        crop_main(arguments, progress=progress)
    report = stream.getvalue().strip()
    outputs = existing_crop_outputs(arguments)
    if outputs:
        report += "\nGenerated patches:\n" + "\n".join(map(str, outputs))
    return report


def existing_crop_outputs(arguments: list[str], progress: Progress | None = None) -> list[Path]:
    """Identify actual crop output files that the operation would replace."""
    from skelhub.postprocessing.crop_escaping_graph_patches import (
        _component_crops, _patch_filename, check_graph_nodes, label_foreground, load_graph, load_nifti,
    )
    options = {arguments[index]: arguments[index + 1]
               for index in range(len(arguments) - 1)
               if arguments[index].startswith("--") and arguments[index] != "--rasterization"
               and not arguments[index + 1].startswith("--")}
    if progress:
        progress(10, "Reading foreground and component labels for output scan")
    foreground = load_nifti(options["--input-fore"], label="--input-fore")
    labels, objects = label_foreground(foreground.data)
    if progress:
        progress(45, f"Foreground has {len([obj for obj in objects if obj is not None])} components")
    checked = check_graph_nodes(load_graph(options["--input-graph"], label="--input-graph"), foreground.data, labels)
    if progress:
        progress(75, f"Found {sum(map(len, checked.escaping_by_component.values()))} escaping nodes in {len(checked.escaping_by_component)} components")
    crops = _component_crops(sorted(checked.escaping_by_component), objects, foreground.data.shape, checked.escaping_by_component)
    candidates: list[Path] = []
    for crop in crops:
        for prefix, directory, suffix in (
            ("foreground", "--nif-path", ".nii.gz"),
            ("graph", "--grapa-path", ".graphml"),
            ("graph2", "--grapa-path", ".graphml"),
            ("image", "--img-path", ".nii.gz"),
            ("graph", "--skel-path", ".nii.gz"),
            ("graph2", "--skel-path", ".nii.gz"),
        ):
            if directory not in options:
                continue
            if prefix == "graph2" and "--input-graph2" not in options:
                continue
            if prefix == "image" and "--input-img" not in options:
                continue
            candidates.append(Path(options[directory]) / _patch_filename(prefix, crop, suffix))
    existing = [candidate for candidate in candidates if candidate.exists()]
    if progress:
        progress(95, f"Output scan complete: {len(existing)} existing files would be replaced")
    return existing
