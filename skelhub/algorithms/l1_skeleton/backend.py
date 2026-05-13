"""Framework adapter for the Python-native L1-medial skeleton backend."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

import numpy as np

from skelhub.core import SkeletonResult, VolumeData

from .config import L1SkeletonConfig
from .rasterize import rasterize_l1_points
from .skeleton import run_l1_skeleton


class L1SkeletonBackend:
    """SkelHub adapter for the L1-medial skeleton core v1 implementation."""

    name = "l1_skeleton"

    def build_config(self, args: Any) -> L1SkeletonConfig:
        """Create a validated config from argparse-style inputs or dicts."""
        if isinstance(args, L1SkeletonConfig):
            return args.validate()
        if isinstance(args, dict):
            return L1SkeletonConfig(**args).validate()
        return L1SkeletonConfig(
            sample_count=getattr(args, "l1_sample_count", 512),
            initial_radius=getattr(args, "l1_initial_radius", None),
            radius_growth=getattr(args, "l1_radius_growth", 1.5),
            max_radius=getattr(args, "l1_max_radius", None),
            max_iterations=getattr(args, "l1_max_iterations", 80),
            stop_error=getattr(args, "l1_stop_error", 0.01),
            repulsion_mu=getattr(args, "l1_repulsion_mu", 0.35),
            repulsion_mu_min=getattr(args, "l1_repulsion_mu_min", 0.15),
            random_seed=getattr(args, "l1_random_seed", 0),
        ).validate()

    def run(
        self,
        volume: VolumeData,
        config: L1SkeletonConfig,
        log: Callable[[str], None] | None = None,
    ) -> SkeletonResult:
        """Run L1 skeletonization and return a standard SkelHub result."""
        data = np.asarray(volume.data)
        if data.ndim != 3:
            raise ValueError("The l1_skeleton backend expects a 3D volume.")

        started = time.perf_counter()
        warnings: list[str] = []
        binary = data > 0
        foreground_voxels = np.argwhere(binary)

        if len(foreground_voxels) == 0:
            warnings.append("Input volume contained no foreground voxels.")
            skeleton = np.zeros(data.shape, dtype=np.uint8)
            metadata: dict[str, object] = {
                "input_foreground_voxels": 0,
                "sample_count": 0,
                "iterations": 0,
                "radius_stages": 0,
                "final_radius": 0.0,
                "last_movement_error": 0.0,
                "converged": True,
                "hit_iteration_cap": False,
                "output_points": 0,
                "implementation": "Python-native L1-medial skeleton core v1",
                "deferred_features": ["density weighting", "ellipse re-centering", "reference branch search"],
            }
        else:
            spacing = volume.spacing if volume.spacing is not None else (1.0, 1.0, 1.0)
            spacing = tuple(float(value) for value in spacing)
            if log:
                log("Running Python-native L1-medial skeleton core v1...")
            run_result = run_l1_skeleton(
                foreground_voxels,
                spacing=spacing,
                config=config,
            )
            skeleton = rasterize_l1_points(run_result.points, data.shape)
            metadata = dict(run_result.metadata)
            metadata["output_foreground_voxels"] = int(np.count_nonzero(skeleton))

            if metadata.get("hit_iteration_cap"):
                warnings.append("L1 skeletonization hit the configured max_iterations cap.")
            if int(metadata.get("output_foreground_voxels", 0)) == 0:
                warnings.append("L1 point rasterization produced no skeleton voxels.")

        elapsed = time.perf_counter() - started

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
            backend_metadata={"config": asdict(config), "l1_skeleton": metadata},
        )
