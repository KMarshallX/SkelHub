"""Framework adapter for the flux-driven medial curve backend."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

import numpy as np

from skelhub.core import SkeletonResult, VolumeData

from .config import FluxConfig
from .medial_curve import extract_medial_curve


class FluxBackend:
    """Framework-facing adapter for flux-driven medial curve extraction."""

    name = "flux"

    def build_config(self, args: Any) -> FluxConfig:
        """Create a validated config from argparse-style inputs or dicts."""
        if isinstance(args, FluxConfig):
            return args.validate()
        if isinstance(args, dict):
            return FluxConfig(**args).validate()
        return FluxConfig(
            threshold=getattr(args, "flux_threshold", 0.0),
            sigma=getattr(args, "flux_sigma", 0.5),
            sigma_unit=getattr(args, "flux_sigma_unit", "physical"),
        ).validate()

    def run(
        self,
        volume: VolumeData,
        config: FluxConfig,
        log: Callable[[str], None] | None = None,
    ) -> SkeletonResult:
        """Run flux-driven medial curve extraction on a standardized 3D volume."""
        data = np.asarray(volume.data)
        if data.ndim != 3:
            raise ValueError("The flux backend expects a 3D volume.")
        if 0 in data.shape:
            raise ValueError("The flux backend expects non-empty dimensions.")

        config = config.validate()
        if not np.all((data == 0) | (data == 1)):
            raise ValueError("The flux backend expects an exactly binary input volume with values {0, 1}.")

        started = time.perf_counter()
        warnings: list[str] = []
        binary = data.astype(bool, copy=False)
        input_voxels = int(np.count_nonzero(binary))

        if input_voxels == 0:
            warnings.append("Input volume contained no foreground voxels.")
            skeleton = np.zeros_like(binary, dtype=np.uint8)
            flux_stats = None
        else:
            if log:
                log("Running flux-driven medial curve extraction...")
            skeleton, flux_stats = extract_medial_curve(
                binary,
                config,
                spacing=volume.spacing,
                log=log,
            )

        output_voxels = int(np.count_nonzero(skeleton))
        elapsed = time.perf_counter() - started

        flux_metadata: dict[str, Any] = {
            "implementation": "Python-native flux-driven medial curve extraction",
            "source_reference": (
                "VMTK/EvoLib medial-curve behavior; Bouix, Siddiqi, and Tannenbaum "
                "flux-driven automatic centerline extraction"
            ),
            "copied_vmtk_source": False,
            "input_foreground_voxels": input_voxels,
            "output_foreground_voxels": output_voxels,
            "distance": "signed Euclidean distance; foreground <= 0, background > 0",
            "average_outward_flux": "26-neighborhood flux from smoothed signed-distance gradient",
            "topology": "26-connected foreground simplicity and 18-neighborhood/6-connected background simplicity",
        }
        if flux_stats is not None:
            flux_metadata.update(
                {
                    "queued_initial_voxels": flux_stats.queued_initial_voxels,
                    "deleted_voxels": flux_stats.deleted_voxels,
                    "preserved_endpoint_voxels": flux_stats.preserved_endpoint_voxels,
                    "aof_min": flux_stats.aof_min,
                    "aof_max": flux_stats.aof_max,
                    "sigma_voxels": flux_stats.sigma_voxels,
                }
            )

        return SkeletonResult(
            algorithm_name=self.name,
            skeleton=skeleton.astype(np.uint8, copy=False),
            input_metadata={
                "path": volume.path,
                "shape": tuple(int(v) for v in data.shape),
                "spacing": volume.spacing,
            },
            runtime_stats={"wall_clock_seconds": float(elapsed)},
            warnings=warnings,
            backend_metadata={
                "config": asdict(config),
                "flux": flux_metadata,
            },
        )
