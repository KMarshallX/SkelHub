from __future__ import annotations

import numpy as np
import pytest
from igraph import Graph

from skelhub.algorithms.laplacian.backend import LaplacianBackend
from skelhub.algorithms.laplacian.config import LaplacianConfig
from skelhub.algorithms.laplacian.contract_graph import ContractGraph, MAX_CONTRACTION_ITERATIONS
from skelhub.algorithms.laplacian.generate_graph import GenerateGraph
from skelhub.algorithms.laplacian.graph import GeometricGraph
from skelhub.algorithms.laplacian.tools import cumulative_small_cycle_area
from skelhub.core import VolumeData


def _volume(data: np.ndarray) -> VolumeData:
    return VolumeData(
        data=data,
        affine=np.eye(4),
        header=None,
        path="synthetic.nii.gz",
        spacing=(1.0, 1.0, 1.0),
    )


def _fake_skeletonize_graph(mask: np.ndarray, **kwargs):
    coords = np.argwhere(mask)
    graph = GeometricGraph()
    graph.add_nodes_from([0, 1])
    graph.nodes[0]["pos"] = coords[0].astype(float)
    graph.nodes[0]["r"] = 1.0
    graph.nodes[1]["pos"] = coords[-1].astype(float)
    graph.nodes[1]["r"] = 1.0
    graph.add_edge(0, 1)
    metadata = {
        "initial_nodes": 2,
        "initial_edges": 1,
        "refined_nodes": 2,
        "refined_edges": 1,
        "cleaned_nodes": 2,
        "cleaned_edges": 1,
        "final_cycle_area": 0.0,
    }
    return graph, graph.copy(), metadata


def test_laplacian_processes_and_merges_connected_components(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "skelhub.algorithms.laplacian.backend.skeletonize_graph",
        _fake_skeletonize_graph,
    )
    data = np.zeros((8, 8, 8), dtype=np.uint8)
    data[1:4, 1, 1] = 1
    data[5, 5:8, 5] = 1
    logs: list[str] = []

    clean_path = tmp_path / "clean.graphml"
    original_path = tmp_path / "original.graphml"
    result = LaplacianBackend().run(
        _volume(data),
        LaplacianConfig(graph_output=str(clean_path), graph_original=str(original_path)),
        log=logs.append,
    )

    assert result.backend_metadata["laplacian"]["num_components"] == 2
    assert result.backend_metadata["laplacian"]["cleaned_nodes"] == 4
    assert int(np.count_nonzero(result.skeleton[1:4, 1, 1])) > 0
    assert int(np.count_nonzero(result.skeleton[5, 5:8, 5])) > 0
    assert clean_path.exists()
    assert original_path.exists()

    clean_graph = Graph.Read_GraphML(str(clean_path))
    assert len(clean_graph.vs) == 4
    assert len(set(clean_graph.vs["laplacian_id"])) == 4
    assert sorted(set(clean_graph.vs["component_index"])) == [1, 2]

    joined_logs = "\n".join(logs)
    assert "component=" in joined_logs
    assert "stage=" not in joined_logs
    assert "construct dense graph" not in joined_logs
    assert "rasterize graph" not in joined_logs


def test_laplacian_empty_input_does_not_write_graphml(monkeypatch, tmp_path):
    def _unexpected_call(*args, **kwargs):
        raise AssertionError("empty input should not run the Laplacian skeletonizer")

    monkeypatch.setattr(
        "skelhub.algorithms.laplacian.backend.skeletonize_graph",
        _unexpected_call,
    )
    data = np.zeros((5, 5, 5), dtype=np.uint8)
    clean_path = tmp_path / "clean.graphml"
    original_path = tmp_path / "original.graphml"

    result = LaplacianBackend().run(
        _volume(data),
        LaplacianConfig(graph_output=str(clean_path), graph_original=str(original_path)),
    )

    assert np.count_nonzero(result.skeleton) == 0
    assert "Input volume contained no foreground voxels." in result.warnings
    assert result.backend_metadata["laplacian"]["num_components"] == 0
    assert not clean_path.exists()
    assert not original_path.exists()


def test_laplacian_contraction_limit_warns_and_keeps_latest_graph():
    graph = GeometricGraph()
    graph.Area = 10
    contract = ContractGraph(graph)
    contract._check_graph = lambda: None
    contract._apply_contraction = lambda: None
    contract._update_topology = lambda resolution: None
    contract._check_iter = lambda: (True, 2.0)

    with pytest.warns(RuntimeWarning, match="750 iterations"):
        contract.Update()

    assert contract.GetOutput() is graph
    assert contract.max_iterations_reached is True
    assert contract.Iteration - 1 == MAX_CONTRACTION_ITERATIONS
    assert contract.final_cycle_area == 2.0


def test_laplacian_initial_graph_area_uses_small_cycle_area():
    mask = np.zeros((2, 2, 2), dtype=np.uint8)
    mask[:, :, 0] = 1

    generate = GenerateGraph(mask)
    generate.UpdateGridGraph(Sampling=1.0)
    graph = generate.GetOutput()

    assert graph.Area == pytest.approx(cumulative_small_cycle_area(graph))
    assert graph.Area != np.count_nonzero(mask)
