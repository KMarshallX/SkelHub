"""Framework adapter for the Palagyi-Kuba thinning backend."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

import numpy as np

from skelhub.core import SkeletonResult, VolumeData

from .config import PalagyiKubaConfig
from .directions import AXIS_MAPPING, SUBITERATION_ORDER
from .templates import CURVE_TEMPLATE_SOURCE, SURFACE_TEMPLATE_SOURCE
from .thinning import thin


class PalagyiKubaBackend:
    """Framework-facing adapter for Palagyi-Kuba 12-subiteration thinning."""

    name = "palagyi_kuba"

    def build_config(self, args: Any) -> PalagyiKubaConfig:
        """Create a validated config from argparse-style inputs or dicts."""
        if isinstance(args, PalagyiKubaConfig):
            return args.validate()
        if isinstance(args, dict):
            return PalagyiKubaConfig(**args).validate()
        return PalagyiKubaConfig(
            mode=getattr(args, "pk_mode", "curve"),
            binarize_threshold=getattr(args, "pk_binarize_threshold", 0.5),
            max_cycles=getattr(args, "pk_max_cycles", None),
        ).validate()

    def run(
        self,
        volume: VolumeData,
        config: PalagyiKubaConfig,
        log: Callable[[str], None] | None = None,
    ) -> SkeletonResult:
        """Run Palagyi-Kuba thinning on a standardized 3D volume."""
        data = np.asarray(volume.data)
        if data.ndim != 3:
            raise ValueError("The palagyi_kuba backend expects a 3D volume.")

        config = config.validate()
        started = time.perf_counter()
        warnings: list[str] = []

        if not np.all((data == 0) | (data == 1)):
            warnings.append(
                "Input volume was not exactly binary; thresholding at the configured pk_binarize_threshold."
            )
        binary = data > config.binarize_threshold
        input_voxels = int(np.count_nonzero(binary))

        if input_voxels == 0:
            warnings.append("Input volume contained no foreground voxels after thresholding.")
            skeleton = np.zeros_like(binary, dtype=np.uint8)
            stats = None
        else:
            if log:
                log(f"Running Palagyi-Kuba {config.mode} thinning...")
            skeleton, stats = thin(binary, config, log=log)
            if stats.reached_max_cycles:
                warnings.append("Palagyi-Kuba thinning stopped at pk_max_cycles before convergence.")

        output_voxels = int(np.count_nonzero(skeleton))
        elapsed = time.perf_counter() - started

        template_sources = {
            "curve": CURVE_TEMPLATE_SOURCE,
            "surface": SURFACE_TEMPLATE_SOURCE,
        }
        backend_metadata: dict[str, Any] = {
            "config": asdict(config),
            "palagyi_kuba": {
                "mode": config.mode,
                "template_source": template_sources[config.mode],
                "subiteration_order": list(SUBITERATION_ORDER),
                "axis_mapping": AXIS_MAPPING,
                "input_foreground_voxels": input_voxels,
                "output_foreground_voxels": output_voxels,
                "cycle_count": 0 if stats is None else stats.cycle_count,
                "reached_max_cycles": False if stats is None else stats.reached_max_cycles,
                "per_direction_deletions": (
                    {direction: [] for direction in SUBITERATION_ORDER}
                    if stats is None
                    else stats.per_direction_deletions
                ),
            },
        }

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
            backend_metadata=backend_metadata,
        )
