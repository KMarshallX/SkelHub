"""GUI-facing operations using the same services as the helper scripts."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Callable

import numpy as np

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


@dataclass(frozen=True, slots=True)
class NiftiHeaderPreview:
    """Header facts shown before evaluation; the voxel array is not read.

    ``file_key`` (resolved path, mtime, size) identifies the file version that
    was inspected. ``error`` is set when the header cannot be used.
    """

    path: str
    file_key: tuple[str, int, int] | None
    shape: tuple[int, ...] = ()
    header_unit: str = "unknown"
    stored_spacing: tuple[float, float, float] | None = None
    error: str | None = None


def file_identity(path: str) -> tuple[str, int, int] | None:
    """Resolved path, modification time and size, or None when unreadable."""
    try:
        resolved = Path(path).resolve()
        stat = resolved.stat()
    except OSError:
        return None
    return str(resolved), int(stat.st_mtime_ns), int(stat.st_size)


def inspect_nifti_header(path: str) -> NiftiHeaderPreview:
    """Read shape, spatial unit and stored spacing from a NIfTI header.

    Stored spacing is the affine column lengths in the header's own unit, the
    same values the evaluator converts. Nothing is validated beyond what a
    preview needs; the evaluator remains authoritative.
    """
    import nibabel as nib

    from skelhub.evaluation.validation import header_spatial_unit

    text = path.strip()
    key = file_identity(text) if text else None
    if not text:
        return NiftiHeaderPreview(path=text, file_key=None, error="Select a file.")
    if not text.lower().endswith((".nii", ".nii.gz")):
        return NiftiHeaderPreview(path=text, file_key=key, error="Select a .nii or .nii.gz file.")
    if key is None or not Path(text).is_file():
        return NiftiHeaderPreview(path=text, file_key=None, error="File not found.")
    try:
        image = nib.load(text)
        shape = tuple(int(size) for size in image.shape)
        affine = np.asarray(image.affine, dtype=float)
        header_unit = header_spatial_unit(image.header)
    except Exception as exc:  # nibabel raises several concrete types for unreadable files
        return NiftiHeaderPreview(path=text, file_key=key, error=f"Unable to read NIfTI header: {exc}")
    if len(shape) != 3:
        return NiftiHeaderPreview(path=text, file_key=key, shape=shape, header_unit=header_unit,
                                  error=f"Skeleton must be a 3D volume; got shape {shape}.")
    spacing = None
    if affine.shape == (4, 4) and np.isfinite(affine).all():
        spacing = tuple(float(value) for value in np.linalg.norm(affine[:3, :3], axis=0))
    return NiftiHeaderPreview(path=text, file_key=key, shape=shape, header_unit=header_unit, stored_spacing=spacing)
