"""Framework adapter for the VascGraph Laplacian skeletonization backend."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

import numpy as np

from skelhub.core import GraphResult, SkeletonResult, VolumeData

from .components import (
    aggregate_component_graphs,
    bbox_metadata,
    bbox_start,
    component_mask,
    label_components,
)
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
            stop_param=getattr(args, "stop_param", 0.0015),
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

        if input_voxels == 0:
            warnings.append("Input volume contained no foreground voxels.")
            skeleton = np.zeros_like(binary, dtype=np.uint8)
            graph = None
            original_graph = None
            graph_metadata = {
                "num_components": 0,
                "components": [],
                "initial_nodes": 0,
                "initial_edges": 0,
                "refined_nodes": 0,
                "refined_edges": 0,
                "cleaned_nodes": 0,
                "cleaned_edges": 0,
                "final_cycle_area": 0.0,
                "max_iterations_hits": 0,
                "max_contraction_iterations": 0,
            }
        else:
            labeled, components = label_components(binary)
            progress = (
                LaplacianProgress(log=log, total_components=len(components), started=started)
                if log
                else None
            )
            if progress:
                progress.found(foreground_voxels=input_voxels)

            skeleton = np.zeros_like(binary, dtype=np.uint8)
            cleaned_graph_items = []
            original_graph_items = []
            component_metadata = []

            for component_index, component in enumerate(components, start=1):
                bbox = component.bbox
                crop_mask = component_mask(labeled, component)
                offset = bbox_start(bbox)
                bbox_info = bbox_metadata(bbox)

                if progress:
                    progress.start_component(
                        index=component_index,
                        component_label=component.label,
                        voxel_count=component.voxel_count,
                        bbox=bbox_info,
                    )

                component_started = time.perf_counter()
                component_graph, component_original_graph, metadata = skeletonize_graph(
                    crop_mask,
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
                    progress=None,
                )
                skeleton_crop = rasterize_graph_26conn(component_original_graph, crop_mask.shape)
                skeleton[bbox] |= skeleton_crop.astype(np.uint8, copy=False)
                component_elapsed = time.perf_counter() - component_started
                component_output_voxels = int(np.count_nonzero(skeleton_crop))

                if component_graph is not None and component_graph.number_of_nodes():
                    cleaned_graph_items.append((component_graph, offset, component_index, component.label))
                if component_original_graph is not None and component_original_graph.number_of_nodes():
                    original_graph_items.append((component_original_graph, offset, component_index, component.label))

                component_summary = {
                    "component_index": int(component_index),
                    "component_label": int(component.label),
                    "input_voxels": int(component.voxel_count),
                    "output_voxels": component_output_voxels,
                    "bbox": bbox_info,
                    "wall_clock_seconds": float(component_elapsed),
                    **metadata,
                }
                component_metadata.append(component_summary)
                if metadata.get("max_iterations_reached"):
                    warnings.append(
                        "Laplacian component "
                        f"{component_index} (label={component.label}) reached "
                        f"{metadata.get('max_contraction_iterations', 'the')} "
                        "contraction iteration limit; using the latest contracted graph."
                    )

                if progress:
                    progress.finish_component(
                        index=component_index,
                        component_label=component.label,
                        output_voxels=component_output_voxels,
                        elapsed_seconds=component_elapsed,
                        cleaned_nodes=metadata.get("cleaned_nodes", 0),
                        cleaned_edges=metadata.get("cleaned_edges", 0),
                    )

            graph = aggregate_component_graphs(cleaned_graph_items)
            original_graph = aggregate_component_graphs(original_graph_items)
            graph_metadata = {
                "num_components": len(components),
                "components": component_metadata,
                "initial_nodes": int(sum(item["initial_nodes"] for item in component_metadata)),
                "initial_edges": int(sum(item["initial_edges"] for item in component_metadata)),
                "refined_nodes": int(sum(item["refined_nodes"] for item in component_metadata)),
                "refined_edges": int(sum(item["refined_edges"] for item in component_metadata)),
                "cleaned_nodes": int(sum(item["cleaned_nodes"] for item in component_metadata)),
                "cleaned_edges": int(sum(item["cleaned_edges"] for item in component_metadata)),
                "final_cycle_area": float(sum(item["final_cycle_area"] for item in component_metadata)),
                "max_iterations_hits": int(
                    sum(bool(item.get("max_iterations_reached")) for item in component_metadata)
                ),
                "max_contraction_iterations": int(
                    max(
                        (int(item.get("max_contraction_iterations", 0)) for item in component_metadata),
                        default=0,
                    )
                ),
            }

        graph_output_path = None
        if config.graph_output and graph is not None:
            write_laplacian_graphml(graph, config.graph_output, volume.affine, binary.shape)
            graph_output_path = str(config.graph_output)

        graph_original_path = None
        if config.graph_original and original_graph is not None:
            write_laplacian_graphml(
                original_graph,
                config.graph_original,
                volume.affine,
                binary.shape,
                include_centerline_voxel_points=True,
            )
            graph_original_path = str(config.graph_original)

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
        if input_voxels and progress:
            progress.finish_all(output_voxels=output_voxels, runtime_seconds=elapsed)
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
