"""Framework adapter for the VascGraph Laplacian skeletonization backend."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

import numpy as np

from skelhub.core import GraphResult, SkeletonResult, VolumeData

from .config import LaplacianConfig
from .graphml import write_laplacian_graphml
from .progress import LaplacianProgress
from .rasterize import rasterize_graph_26conn
from .skeleton import skeletonize_graph


class LaplacianBackend:
    """SkelHub adapter around VascGraph's Laplacian graph-contraction path."""

    name = "laplacian"

    def build_config(self, args: Any) -> LaplacianConfig:
        """Create a validated config from argparse-style inputs or dicts."""
        if isinstance(args, LaplacianConfig):
            return args.validate()
        if isinstance(args, dict):
            return LaplacianConfig(**args).validate()
        return LaplacianConfig(
            speed_param=getattr(args, "speed_param", 0.05),
            dist_param=getattr(args, "dist_param", 0.5),
            med_param=getattr(args, "med_param", 0.5),
            degree_threshold=getattr(args, "degree_threshold", 5.0),
            sampling=getattr(args, "sampling", 1.0),
            clustering_r=getattr(args, "clustering_r", 1.0),
            stop_param=getattr(args, "stop_param", 0.001),
            n_free_iteration=getattr(args, "n_free_iteration", 0),
            area_param=getattr(args, "area_param", 50.0),
            poly_param=getattr(args, "poly_param", 10),
            graph_output=getattr(args, "graph_output", None),
            graph_original=getattr(args, "graph_original", None),
        ).validate()

    def run(
        self,
        volume: VolumeData,
        config: LaplacianConfig,
        log: Callable[[str], None] | None = None,
    ) -> SkeletonResult:
        """Run Laplacian graph contraction and return a standard skeleton result."""
        data = np.asarray(volume.data)
        if data.ndim != 3:
            raise ValueError("The laplacian backend expects a 3D volume.")

        started = time.perf_counter()
        warnings = []
        binary = data > 0
        input_voxels = int(np.count_nonzero(binary))
        stages = ["prepare input"]
        if input_voxels:
            stages.extend(("construct dense graph", "contract graph", "refine graph", "clean graph", "rasterize graph"))
            if config.graph_output:
                stages.append("write cleaned graph")
            if config.graph_original:
                stages.append("write refined graph")
        stages.append("assemble result")
        progress = LaplacianProgress(log=log, stages=tuple(stages), started=started) if log else None
        if progress:
            progress.start("prepare input")
            progress.finish(f"foreground_voxels={input_voxels}")

        if input_voxels == 0:
            warnings.append("Input volume contained no foreground voxels.")
            skeleton = np.zeros_like(binary, dtype=np.uint8)
            graph = None
            original_graph = None
            graph_metadata = {
                "initial_nodes": 0,
                "initial_edges": 0,
                "refined_nodes": 0,
                "refined_edges": 0,
                "cleaned_nodes": 0,
                "cleaned_edges": 0,
                "final_cycle_area": 0.0,
            }
        else:
            graph, original_graph, graph_metadata = skeletonize_graph(
                binary,
                speed_param=config.speed_param,
                dist_param=config.dist_param,
                med_param=config.med_param,
                sampling=config.sampling,
                degree_threshold=config.degree_threshold,
                clustering_r=config.clustering_r,
                stop_param=config.stop_param,
                n_free_iteration=config.n_free_iteration,
                area_param=config.area_param,
                poly_param=config.poly_param,
                progress=progress,
            )
            if progress:
                progress.start("rasterize graph")
            skeleton = rasterize_graph_26conn(original_graph, binary.shape)
            if progress:
                progress.finish(f"foreground_voxels={int(np.count_nonzero(skeleton))}")

        graph_output_path = None
        if config.graph_output and graph is not None:
            if progress:
                progress.start("write cleaned graph")
            write_laplacian_graphml(graph, config.graph_output, volume.affine, binary.shape)
            graph_output_path = str(config.graph_output)
            if progress:
                progress.finish(f"output={graph_output_path}")

        graph_original_path = None
        if config.graph_original and original_graph is not None:
            if progress:
                progress.start("write refined graph")
            write_laplacian_graphml(original_graph, config.graph_original, volume.affine, binary.shape)
            graph_original_path = str(config.graph_original)
            if progress:
                progress.finish(f"output={graph_original_path}")

        if progress:
            progress.start("assemble result")
        output_voxels = int(np.count_nonzero(skeleton))
        if input_voxels and output_voxels == 0:
            warnings.append("Laplacian graph rasterization produced no skeleton voxels.")

        graph_result = None
        if graph is not None:
            graph_result = GraphResult(
                nodes=[
                    tuple(int(v) for v in np.round(graph.nodes[node]["pos"]).astype(int))
                    for node in graph.GetNodes()
                ],
                edges=[(int(u), int(v)) for u, v in graph.GetEdges()],
                metadata={"coordinate_space": "voxel"},
            )

        metadata = {
            **graph_metadata,
            "input_foreground_voxels": input_voxels,
            "output_foreground_voxels": output_voxels,
            "rasterized_output_source": "graph_original",
            "graph_output": graph_output_path,
            "graph_original": graph_original_path,
        }
        elapsed = time.perf_counter() - started
        if progress:
            progress.finish(f"output_voxels={output_voxels}, runtime={elapsed:.2f}s")
            elapsed = time.perf_counter() - started

        return SkeletonResult(
            algorithm_name=self.name,
            skeleton=skeleton.astype(np.uint8, copy=False),
            input_metadata={
                "path": volume.path,
                "shape": tuple(int(v) for v in volume.data.shape),
                "spacing": volume.spacing,
            },
            runtime_stats={"wall_clock_seconds": float(elapsed)},
            warnings=warnings,
            backend_metadata={"config": asdict(config), "laplacian": metadata},
            graph=graph_result,
        )
