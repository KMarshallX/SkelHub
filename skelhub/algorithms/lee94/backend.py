"""Framework adapter for the scikit-image Lee94 thinning backend."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

import numpy as np
from skimage.morphology import skeletonize

from skelhub.core import SkeletonResult, VolumeData

from .config import Lee94Config


class Lee94Backend:
    """Thin framework-facing adapter for scikit-image's Lee94 skeletonization."""

    name = "lee94"

    def build_config(self, args: Any) -> Lee94Config:
        """Create a validated config from argparse-style inputs or dicts."""
        if isinstance(args, Lee94Config):
            return args.validate()
        if isinstance(args, dict):
            return Lee94Config(**args).validate()
        return Lee94Config(
            binarize_threshold=getattr(args, "binarize_threshold", 0.5),
        ).validate()

    def run(
        self,
        volume: VolumeData,
        config: Lee94Config,
        log: Callable[[str], None] | None = None,
    ) -> SkeletonResult:
        """Run the Lee94 backend on a standardized volume."""
        data = np.asarray(volume.data)
        if data.ndim != 3:
            raise ValueError("The lee94 backend expects a 3D volume.")

        started = time.perf_counter()

        warnings = []
        if not np.all((data == 0) | (data == 1)):
            warnings.append(
                "Input volume was not exactly binary; thresholding at the configured binarize_threshold."
            )

        binary = data > config.binarize_threshold
        input_voxels = int(np.count_nonzero(binary))

        if input_voxels == 0:
            warnings.append("Input volume contained no foreground voxels after thresholding.")
            skeleton = np.zeros_like(binary, dtype=np.uint8)
        else:
            if log:
                log("Running Lee94 skeletonization via scikit-image...")
            skeleton = skeletonize(binary, method="lee").astype(np.uint8, copy=False)

        output_voxels = int(np.count_nonzero(skeleton))
        elapsed = time.perf_counter() - started

        return SkeletonResult(
            algorithm_name=self.name,
            skeleton=skeleton,
            input_metadata={
                "path": volume.path,
                "shape": tuple(int(v) for v in volume.data.shape),
                "spacing": volume.spacing,
            },
            runtime_stats={"wall_clock_seconds": float(elapsed)},
            warnings=warnings,
            backend_metadata={
                "config": asdict(config),
                "lee94": {
                    "implementation": "skimage.morphology.skeletonize(method='lee')",
                    "input_foreground_voxels": input_voxels,
                    "output_foreground_voxels": output_voxels,
                },
            },
        )
