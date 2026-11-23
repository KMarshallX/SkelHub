"""Configuration for the laplskel backend."""

from __future__ import annotations

import math
from dataclasses import dataclass

from skelhub.io.nifti_writer import _ensure_nifti_extension

from .refinement import DEFAULT_FIT_W_H, DEFAULT_FIT_W_H_MEDIAL
from .workflows import _graph_files, validated_output_files

VALID_CONNECTIVITY = (6, 18, 26)
VALID_SOLVER = ("LU", "CG", "AMGCG")
SECOND_FIT_SOLVER = "LU"


def graph_files(path: str, option: str) -> list[str]:
    """Files one graph output writes: ``[path]`` for .graphml, plus ``<stem>_coords.npz`` for .npz."""
    return _graph_files(path, option)


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(slots=True)
class LaplskelConfig:
    """Validated laplskel options, named as on the command line.

    ``w_H`` is upstream's ``w_H_base`` and ``dec_grid_size`` is upstream's
    ``min_edge_length``. ``fit_w_H`` and ``fit_w_H_medial`` stay ``None`` unless
    given; they may only be given together with ``second_fitting``, and then
    default to 0.16 and 3. ``nifti_output`` is the framework's skeleton path. It
    is only used to stop graph files from overwriting it; the CLI fills it in.
    """

    graph_output: str | None = None
    graph_original: str | None = None
    w_L: float = 0.5
    w_H: float = 0.5
    w_H_medial: float = 20.0
    beta_edt: float = 1.0
    max_iter: int = 500
    tol_max_drift: float = 0.05
    tol_mean_drift: float = 0.0025
    decimate_ratio: float = 0.93
    dec_grid_size: float = 0.01
    second_fitting: bool = False
    fit_w_H: float | None = None
    fit_w_H_medial: float | None = None
    init_graph_adj: int = 26
    local_pca_hops: int = 1
    separate_streams: bool = False
    label_connectivity: int = 26
    solver: str = "CG"
    n_jobs: int | None = None
    nifti_output: str | None = None

    @property
    def effective_fit_w_H(self) -> float:
        """Second-fit baseline retention weight actually used."""
        return DEFAULT_FIT_W_H if self.fit_w_H is None else float(self.fit_w_H)

    @property
    def effective_fit_w_H_medial(self) -> float:
        """Second-fit medial retention boost actually used."""
        return DEFAULT_FIT_W_H_MEDIAL if self.fit_w_H_medial is None else float(self.fit_w_H_medial)

    def reserved_outputs(self) -> list[str]:
        """Files the framework writes, which graph outputs must not collide with."""
        return [] if self.nifti_output is None else [_ensure_nifti_extension(self.nifti_output)]

    def validate(self) -> "LaplskelConfig":
        """Apply upstream laplskel's command-line and workflow checks; return self."""
        supplied = [name for name in ("fit_w_H", "fit_w_H_medial") if getattr(self, name) is not None]
        if supplied and not self.second_fitting:
            verb = "require" if len(supplied) > 1 else "requires"
            raise ValueError(" and ".join(f"--{name}" for name in supplied) + f" {verb} --second_fitting.")
        for name in ("max_iter", "local_pca_hops"):
            value = getattr(self, name)
            if not _is_integer(value) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        for name in ("init_graph_adj", "label_connectivity"):
            if getattr(self, name) not in VALID_CONNECTIVITY or isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be one of 6, 18 or 26.")
        if self.solver not in VALID_SOLVER:
            raise ValueError("solver must be one of LU, CG or AMGCG.")
        if self.n_jobs is not None and not _is_integer(self.n_jobs):
            raise ValueError("n_jobs must be an integer or None.")
        if not math.isfinite(self.decimate_ratio) or not 0 < self.decimate_ratio <= 1:
            raise ValueError("decimate_ratio must be finite and in (0, 1].")
        if not math.isfinite(self.tol_mean_drift) or self.tol_mean_drift < 0:
            raise ValueError("tol_mean_drift must be finite and >= 0.")
        if not math.isfinite(self.effective_fit_w_H) or self.effective_fit_w_H <= 0:
            raise ValueError("fit_w_H must be finite and > 0.")
        if not math.isfinite(self.effective_fit_w_H_medial) or self.effective_fit_w_H_medial < 1:
            raise ValueError("fit_w_H_medial must be finite and >= 1.")
        if self.separate_streams and self.label_connectivity != 26:
            raise ValueError("Tunnel preservation requires --label_connectivity 26 when separating streams.")
        if self.graph_output is not None:
            _graph_files(self.graph_output, "--graph_output")
        if self.graph_original is not None:
            _graph_files(self.graph_original, "--graph_original")
        validated_output_files(self.graph_output, self.graph_original, self.reserved_outputs())
        return self
