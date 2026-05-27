"""SkelHub-facing VascGraph Laplacian skeletonization path."""

from __future__ import annotations

import numpy as np

from .contract_graph import ContractGraph
from .generate_graph import GenerateGraph
from .progress import LaplacianProgress
from .refine_graph import RefineGraph
from .tools import fix_graph, post_node_cleaning


def skeletonize_graph(
    mask: np.ndarray,
    *,
    speed_param: float,
    dist_param: float,
    med_param: float,
    sampling: float,
    degree_threshold: float,
    clustering_r: float,
    stop_param: float,
    n_free_iteration: int,
    area_param: float,
    poly_param: int,
    progress: LaplacianProgress | None = None,
):
    """Run dense graph generation, Laplacian contraction, refinement, and cleaning."""
    binary = np.asarray(mask) > 0
    if progress:
        progress.start("construct dense graph")
    generate = GenerateGraph(binary)
    generate.UpdateGridGraph(Sampling=sampling)
    initial_graph = generate.GetOutput()
    if progress:
        progress.finish(
            f"nodes={initial_graph.number_of_nodes()}, edges={initial_graph.number_of_edges()}"
        )

    if progress:
        progress.start("contract graph")
    contract = ContractGraph(initial_graph)
    contract.Update(
        DistParam=dist_param,
        MedParam=med_param,
        SpeedParam=speed_param,
        DegreeThreshold=degree_threshold,
        ClusteringResolution=clustering_r,
        StopParam=stop_param,
        NFreeIteration=n_free_iteration,
        progress=progress,
    )
    contracted_graph = contract.GetOutput()
    if progress:
        progress.finish(f"iterations={contract.Iteration - 1}, cycle_area={contract.final_cycle_area:.3f}")

    if progress:
        progress.start("refine graph")
    refine = RefineGraph(contracted_graph)
    refine.Update(AreaParam=area_param, PolyParam=poly_param)
    refined_graph = fix_graph(refine.GetOutput())
    if progress:
        progress.finish(f"nodes={refined_graph.number_of_nodes()}, edges={refined_graph.number_of_edges()}")

    if progress:
        progress.start("clean graph")
    cleaned_graph = post_node_cleaning(refined_graph)
    if progress:
        progress.finish(f"nodes={cleaned_graph.number_of_nodes()}, edges={cleaned_graph.number_of_edges()}")

    metadata = {
        "initial_nodes": int(initial_graph.number_of_nodes()),
        "initial_edges": int(initial_graph.number_of_edges()),
        "refined_nodes": int(refined_graph.number_of_nodes()),
        "refined_edges": int(refined_graph.number_of_edges()),
        "cleaned_nodes": int(cleaned_graph.number_of_nodes()),
        "cleaned_edges": int(cleaned_graph.number_of_edges()),
        "final_cycle_area": float(getattr(contract, "final_cycle_area", 0.0)),
    }
    return cleaned_graph, refined_graph, metadata
