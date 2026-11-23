"""SkelHub adapter for the laplskel Laplacian-flow skeletonisation backend."""

from __future__ import annotations

import contextlib
import io
import time
import warnings
from dataclasses import asdict, dataclass
from typing import Any, Callable

import nibabel as nib
import numpy as np
from scipy import sparse

from skelhub.core import GraphResult, SkeletonResult, VolumeData
from skelhub.io import read_nifti

from .config import SECOND_FIT_SOLVER, LaplskelConfig
from .workflows import _graph_files, laplacian_skeletonisation_from_mask

_CONFIG_FIELDS = tuple(LaplskelConfig.__dataclass_fields__)


@dataclass(slots=True)
class SourceMask:
    """The foreground mask exactly as upstream laplskel would load it."""

    mask: np.ndarray
    affine: np.ndarray
    spacing: tuple[float, float, float]
    source: str
    normalized_foreground_differences: int | None


def _squeezed_3d(data: np.ndarray, name: str) -> np.ndarray:
    """Squeeze singleton axes and require 3D, like ``nigsp.io.check_nifti_dim``."""
    squeezed = np.asarray(data).squeeze()
    if squeezed.ndim != 3:
        raise ValueError(f"A 3D nifti file is required, but {name} is {squeezed.ndim}D. Please check the input file.")
    return squeezed


def _same_values(first: Any, second: Any) -> bool:
    """Array equality that treats NaN as equal to NaN where the dtype allows it."""
    first, second = np.asarray(first), np.asarray(second)
    try:
        return bool(np.array_equal(first, second, equal_nan=True))
    except TypeError:
        return bool(np.array_equal(first, second))


def load_source_mask(volume: VolumeData) -> SourceMask:
    """Build the laplskel foreground mask: every non-zero voxel is foreground.

    Upstream loads masks with ``nibabel.load(path).get_fdata()``, squeezes
    singleton axes, requires 3D and keeps ``data != 0`` (negative values and
    NaN count as foreground). SkelHub's path reader rescales non-binary
    intensities to [0, 1], which can change that mask. So when ``volume.path``
    is set, the mask is rebuilt from the file the upstream way, after checking
    that ``volume`` still holds exactly what SkelHub read from that file. When
    ``volume.path`` is None, ``volume.data`` itself is the mask source.
    """
    if volume.path is None:
        data = _squeezed_3d(volume.data, "the input volume")
        mask = data != 0
        affine = np.asarray(volume.affine, dtype=float)
        if volume.spacing is not None:
            spacing = tuple(float(v) for v in volume.spacing)
        elif volume.header is not None:
            spacing = tuple(float(v) for v in volume.header.get_zooms()[:3])
        else:
            spacing = (1.0, 1.0, 1.0)
        return SourceMask(mask, affine, spacing, "volume_data", None)

    path = str(volume.path)
    expected_data, expected_affine, _ = read_nifti(path)
    if not (
        np.shape(volume.data) == expected_data.shape
        and _same_values(volume.data, expected_data)
        and _same_values(volume.affine, expected_affine)
    ):
        raise ValueError(
            f"VolumeData does not match its source file {path!r}; laplskel rebuilds the mask "
            "from that file. Set VolumeData.path to None to skeletonise the in-memory array."
        )
    image = nib.load(path)
    mask = _squeezed_3d(image.get_fdata(), path) != 0
    normalized = _squeezed_3d(volume.data, path) > 0
    return SourceMask(
        mask=mask,
        affine=image.affine,
        spacing=image.header.get_zooms()[:3],  # as upstream passes it (unused by refinement)
        source="file",
        normalized_foreground_differences=int(np.count_nonzero(normalized != mask)),
    )


def _config_from_namespace(args: Any) -> LaplskelConfig:
    values = {name: getattr(args, name) for name in _CONFIG_FIELDS if name != "nifti_output" and hasattr(args, name)}
    output = getattr(args, "output", None)
    if output is not None:
        values["nifti_output"] = str(output)
    return LaplskelConfig(**values)


class LaplskelBackend:
    """Laplacian-flow contraction, topology-preserving thinning and optional second fit."""

    name = "laplskel"

    def build_config(self, args: Any) -> LaplskelConfig:
        """Create a validated config from argparse args, a dict or a config."""
        if isinstance(args, LaplskelConfig):
            return args.validate()
        if isinstance(args, dict):
            return LaplskelConfig(**args).validate()
        return _config_from_namespace(args).validate()

    def run(
        self,
        volume: VolumeData,
        config: LaplskelConfig,
        log: Callable[[str], None] | None = None,
    ) -> SkeletonResult:
        """Skeletonise the volume and write any requested graph files."""
        config = self.build_config(config)
        started = time.perf_counter()
        source = load_source_mask(volume)
        result_warnings: list[str] = []
        if source.normalized_foreground_differences:
            result_warnings.append(
                f"SkelHub's rescaled input would differ from laplskel's non-zero foreground in "
                f"{source.normalized_foreground_differences} voxels; the non-zero rule was used."
            )
        if log:
            log(
                f"laplskel: mask from {source.source}, shape={source.mask.shape}, "
                f"foreground_voxels={int(np.count_nonzero(source.mask))}"
            )
            if volume.path is not None:
                print(f"Ingesting NIfTI image: {volume.path}")

        quiet = log is None
        output = contextlib.nullcontext() if log else contextlib.redirect_stdout(io.StringIO())
        with warnings.catch_warnings(record=True) as caught, output:
            warnings.simplefilter("always")
            coordinates, adjacency, skeleton, components = laplacian_skeletonisation_from_mask(
                source.mask,
                source.affine,
                source.spacing,
                beta_edt=config.beta_edt,
                w_L=config.w_L,
                w_H_base=config.w_H,
                w_H_medial=config.w_H_medial,
                tol_max_drift=config.tol_max_drift,
                tol_mean_drift=config.tol_mean_drift,
                max_iter=config.max_iter,
                decimate_ratio=config.decimate_ratio,
                min_edge_length=config.dec_grid_size,
                separate_streams=config.separate_streams,
                label_connectivity=config.label_connectivity,
                init_graph_adj=config.init_graph_adj,
                local_pca_hops=config.local_pca_hops,
                solver=config.solver,
                n_jobs=config.n_jobs,
                graph_output=config.graph_output,
                graph_original=config.graph_original,
                second_fitting=config.second_fitting,
                fit_w_H=config.effective_fit_w_H,
                fit_w_H_medial=config.effective_fit_w_H_medial,
                reserved_outputs=config.reserved_outputs(),
                quiet=quiet,
            )
        for record in caught:
            result_warnings.append(f"{record.category.__name__}: {record.message}")
            warnings.warn_explicit(record.message, record.category, record.filename, record.lineno)

        upper = sparse.triu(adjacency, k=1).tocoo()
        graph = GraphResult(
            nodes=[tuple(int(v) for v in np.rint(point)) for point in coordinates],
            edges=[(int(u), int(v)) for u, v in zip(upper.row, upper.col)],
            metadata={
                "coordinate_space": "voxel",
                "node_positions": "rounded; exact coordinates are in the --graph_output file",
            },
        )
        skeleton = skeleton.astype(np.uint8)
        elapsed = time.perf_counter() - started
        written = {
            option: None if path is None else _graph_files(path, option)
            for option, path in (("graph_output", config.graph_output), ("graph_original", config.graph_original))
        }
        if log:
            for option, files in written.items():
                if files:
                    log(f"laplskel: {option} written to {', '.join(files)}")

        metadata = {
            "mask_source": source.source,
            "foreground_voxels": int(np.count_nonzero(source.mask)),
            "normalized_foreground_differences": source.normalized_foreground_differences,
            "components_processed": len(components),
            "graph_nodes": int(len(coordinates)),
            "graph_edges": int(upper.nnz),
            "output_foreground_voxels": int(np.count_nonzero(skeleton)),
            "contraction_solver": config.solver,
            "second_fit_solver": SECOND_FIT_SOLVER if config.second_fitting else None,
            "effective_fit_w_H": config.effective_fit_w_H if config.second_fitting else None,
            "effective_fit_w_H_medial": config.effective_fit_w_H_medial if config.second_fitting else None,
            "graph_output_files": written["graph_output"],
            "graph_original_files": written["graph_original"],
        }
        return SkeletonResult(
            algorithm_name=self.name,
            skeleton=skeleton,
            input_metadata={
                "path": volume.path,
                "shape": tuple(int(v) for v in np.shape(volume.data)),
                "spacing": volume.spacing,
            },
            runtime_stats={"wall_clock_seconds": float(elapsed)},
            warnings=result_warnings,
            backend_metadata={"config": asdict(config), "laplskel": metadata},
            graph=graph,
        )
