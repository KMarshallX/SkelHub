"""Framework adapter for the MCP skeletonization backend."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

import numpy as np

from skelhub.core import SkeletonResult, VolumeData

from .config import MCPConfig
from .multi_object import skeletonize_volume


class MCPBackend:
    """Thin framework-facing adapter around the current MCP implementation."""

    name = "mcp"

    def build_config(self, args: Any) -> MCPConfig:
        """Create a validated config from argparse-style inputs or dicts."""
        if isinstance(args, MCPConfig):
            return args.validate()
        if isinstance(args, dict):
            return MCPConfig(**args).validate()
        return MCPConfig(
            root_method=args.root_method,
            threshold_scale=args.threshold_scale,
            dilation_factor=args.dilation_factor,
            max_iterations=args.max_iterations,
            min_object_size=args.min_object_size,
            label_objects=args.label_objects,
        ).validate()

    def run(
        self,
        volume: VolumeData,
        config: MCPConfig,
        log: Callable[[str], None] | None = None,
    ) -> SkeletonResult:
        """Run the MCP backend on a standardized volume."""
        started = time.perf_counter()
        skeleton, metadata = skeletonize_volume(
            np.asarray(volume.data, dtype=np.float32),
            root_method=config.root_method,
            threshold_scale=config.threshold_scale,
            dilation_factor=config.dilation_factor,
            max_iterations=config.max_iterations,
            min_size=config.min_object_size,
            label_objects=config.label_objects,
            log=log,
        )
        elapsed = time.perf_counter() - started
        warnings = []
        if metadata.get("max_iterations_hits"):
            warnings.append("One or more objects hit the configured max_iterations cap.")
        if any(obj.get("safety_fuse_triggered") for obj in metadata.get("objects", [])):
            warnings.append("One or more objects stopped via the MCP safety fuse.")
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
            backend_metadata={"config": asdict(config), "mcp": metadata},
        )
