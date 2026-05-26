"""Tests for dual-space Voreen-style vessel feature extraction."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import igraph as ig
import nibabel as nib
import numpy as np
import pytest

from skelhub.cli.main import main
from skelhub.postprocessing.feature import extract_features_from_paths
from skelhub.postprocessing.feature.assignment import assign_foreground_to_edges
from skelhub.postprocessing.feature.models import FeatureGraph, FeatureGraphEdge, FeatureGraphNode


def _write_volume(path: Path, data: np.ndarray, zooms=(1.0, 1.0, 1.0), unit="mm") -> None:
    affine = np.diag([*zooms, 1.0])
    image = nib.Nifti1Image(data.astype(np.uint8), affine)
    image.header.set_xyzt_units(unit)
    nib.save(image, str(path))


def _write_graph(
    path: Path,
    *,
    source: str = "graphgen",
    node_positions=((1.0, 2.0, 2.0), (5.0, 2.0, 2.0)),
    edge_paths=(((2, 2, 2), (3, 2, 2), (4, 2, 2)),),
    edges=((0, 1),),
) -> None:
    graph = ig.Graph(directed=False)
    graph.add_vertices(len(node_positions))
    node_id_name = "proto_id" if source == "graphgen" else "laplacian_id"
    edge_id_name = "proto_edge_id" if source == "graphgen" else "laplacian_edge_id"
    for node_id, position in enumerate(node_positions):
        graph.vs[node_id][node_id_name] = node_id
        graph.vs[node_id]["voxel_pos"] = json.dumps(list(position))
        graph.vs[node_id]["X"] = float(position[0])
        graph.vs[node_id]["Y"] = float(position[1])
        graph.vs[node_id]["Z"] = float(position[2])
    graph.add_edges(list(edges))
    for edge_id, points in enumerate(edge_paths):
        graph.es[edge_id][edge_id_name] = edge_id
        graph.es[edge_id]["centerline_voxels"] = json.dumps([list(point) for point in points])
    graph.write_graphml(str(path))


def _straight_volumes() -> tuple[np.ndarray, np.ndarray]:
    foreground = np.zeros((7, 5, 5), dtype=np.uint8)
    foreground[1:6, 1:4, 1:4] = 1
    skeleton = np.zeros_like(foreground)
    skeleton[1:6, 2, 2] = 1
    return foreground, skeleton


def test_extract_features_writes_dual_space_graphgen_csv(tmp_path: Path) -> None:
    foreground, skeleton = _straight_volumes()
    foreground_path = tmp_path / "foreground.nii.gz"
    skeleton_path = tmp_path / "skeleton.nii.gz"
    graph_path = tmp_path / "graph.graphml"
    edges_path = tmp_path / "edges.csv"
    nodes_path = tmp_path / "nodes.csv"
    _write_volume(foreground_path, foreground, zooms=(2.0, 1.0, 1.0), unit="mm")
    _write_volume(skeleton_path, skeleton, zooms=(2.0, 1.0, 1.0), unit="mm")
    _write_graph(graph_path)

    result = extract_features_from_paths(foreground_path, skeleton_path, graph_path, edges_path, nodes_path)

    assert result.physical_unit == "mm"
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.length == pytest.approx(4.0)
    assert edge.length_image == pytest.approx(8.0)
    assert edge.curveness == pytest.approx(1.0)
    assert edge.curveness_image == pytest.approx(1.0)
    assert math.isfinite(edge.avgRadius)
    assert math.isfinite(edge.avgRadius_image)
    assert edge.node1_degree == 1
    assert edge.node2_degree == 1

    with edges_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert "length_image_mm" in rows[0]
    assert "avgRadius_image_mm" in rows[0]
    with nodes_path.open(newline="", encoding="utf-8") as stream:
        node_rows = list(csv.DictReader(stream))
    assert node_rows[0] == {
        "id": "0",
        "position_x": "1.0",
        "position_y": "2.0",
        "position_z": "2.0",
        "degree": "1",
    }


def test_accepts_laplacian_graph_output_paths_outside_skeleton(tmp_path: Path) -> None:
    foreground, skeleton = _straight_volumes()
    skeleton[:, :, :] = 0
    skeleton[1:6, 1, 2] = 1
    foreground[1:6, 1, 2] = 1
    foreground_path = tmp_path / "foreground.nii.gz"
    skeleton_path = tmp_path / "skeleton.nii.gz"
    graph_path = tmp_path / "lap.graphml"
    _write_volume(foreground_path, foreground)
    _write_volume(skeleton_path, skeleton)
    _write_graph(
        graph_path,
        source="laplacian",
        node_positions=((1.25, 2.0, 2.0), (4.75, 2.0, 2.0)),
    )

    messages: list[str] = []
    result = extract_features_from_paths(
        foreground_path,
        skeleton_path,
        graph_path,
        tmp_path / "edges.csv",
        tmp_path / "nodes.csv",
        log=messages.append,
    )

    assert result.edges[0].length > 0
    assert result.warnings
    assert any("authoritative feature geometry" in message for message in messages)


def test_empty_edge_path_writes_nan_radii_and_unknown_unit_columns(tmp_path: Path) -> None:
    foreground, skeleton = _straight_volumes()
    foreground_path = tmp_path / "foreground.nii.gz"
    skeleton_path = tmp_path / "skeleton.nii.gz"
    graph_path = tmp_path / "empty.graphml"
    edge_path = tmp_path / "edges.csv"
    _write_volume(foreground_path, foreground, unit="unknown")
    _write_volume(skeleton_path, skeleton, unit="unknown")
    _write_graph(graph_path, edge_paths=((),))

    result = extract_features_from_paths(
        foreground_path, skeleton_path, graph_path, edge_path, tmp_path / "nodes.csv"
    )

    assert math.isnan(result.edges[0].avgRadius)
    assert math.isnan(result.edges[0].avgRadius_image)
    with edge_path.open(newline="", encoding="utf-8") as stream:
        row = next(csv.DictReader(stream))
    assert "length_image_unknown" in row
    assert row["avgRadius"].lower() == "nan"


def test_rejects_skeleton_outside_foreground(tmp_path: Path) -> None:
    foreground, skeleton = _straight_volumes()
    foreground[1, 2, 2] = 0
    foreground_path = tmp_path / "foreground.nii.gz"
    skeleton_path = tmp_path / "skeleton.nii.gz"
    graph_path = tmp_path / "graph.graphml"
    _write_volume(foreground_path, foreground)
    _write_volume(skeleton_path, skeleton)
    _write_graph(graph_path)

    with pytest.raises(ValueError, match="contained"):
        extract_features_from_paths(
            foreground_path, skeleton_path, graph_path, tmp_path / "edges.csv", tmp_path / "nodes.csv"
        )


def test_feature_cli_creates_csv_outputs(tmp_path: Path) -> None:
    foreground, skeleton = _straight_volumes()
    foreground_path = tmp_path / "foreground.nii.gz"
    skeleton_path = tmp_path / "skeleton.nii.gz"
    graph_path = tmp_path / "graph.graphml"
    edge_path = tmp_path / "edges.csv"
    node_path = tmp_path / "nodes.csv"
    _write_volume(foreground_path, foreground)
    _write_volume(skeleton_path, skeleton)
    _write_graph(graph_path)

    status = main(
        [
            "feature",
            "--foreground",
            str(foreground_path),
            "--skeleton",
            str(skeleton_path),
            "--graph",
            str(graph_path),
            "--edge-output",
            str(edge_path),
            "--node-output",
            str(node_path),
        ]
    )

    assert status == 0
    assert edge_path.exists()
    assert node_path.exists()


def test_anisotropic_spacing_can_change_foreground_edge_assignment() -> None:
    foreground = np.ones((3, 4, 1), dtype=bool)
    graph = FeatureGraph(
        source="graphgen",
        nodes=(
            FeatureGraphNode(0, np.asarray((2.0, 0.0, 0.0))),
            FeatureGraphNode(1, np.asarray((2.0, 0.0, 0.0))),
            FeatureGraphNode(2, np.asarray((0.0, 3.0, 0.0))),
            FeatureGraphNode(3, np.asarray((0.0, 3.0, 0.0))),
        ),
        edges=(
            FeatureGraphEdge(0, 0, 1, np.asarray(((2, 0, 0),), dtype=int)),
            FeatureGraphEdge(1, 2, 3, np.asarray(((0, 3, 0),), dtype=int)),
        ),
    )

    voxel_labels = assign_foreground_to_edges(foreground, graph, np.ones(3))
    image_labels = assign_foreground_to_edges(foreground, graph, np.asarray((2.0, 1.0, 1.0)))

    assert voxel_labels[0, 0, 0] == 0
    assert image_labels[0, 0, 0] == 1


def test_curved_path_has_curveness_greater_than_one(tmp_path: Path) -> None:
    foreground = np.zeros((5, 5, 5), dtype=np.uint8)
    path = [(1, 1, 2), (1, 2, 2), (2, 2, 2), (3, 2, 2), (3, 1, 2)]
    for voxel in path:
        foreground[voxel] = 1
    foreground_path = tmp_path / "foreground.nii.gz"
    skeleton_path = tmp_path / "skeleton.nii.gz"
    graph_path = tmp_path / "curved.graphml"
    _write_volume(foreground_path, foreground)
    _write_volume(skeleton_path, foreground)
    _write_graph(
        graph_path,
        node_positions=((1.0, 1.0, 2.0), (3.0, 1.0, 2.0)),
        edge_paths=(((1, 2, 2), (2, 2, 2), (3, 2, 2)),),
    )

    result = extract_features_from_paths(
        foreground_path, skeleton_path, graph_path, tmp_path / "edges.csv", tmp_path / "nodes.csv"
    )

    assert result.edges[0].length == pytest.approx(4.0)
    assert result.edges[0].curveness == pytest.approx(2.0)


def test_edge_degrees_are_associated_with_named_endpoint_ids(tmp_path: Path) -> None:
    foreground = np.zeros((5, 5, 5), dtype=np.uint8)
    voxels = [(2, 2, 2), (1, 2, 2), (3, 2, 2)]
    for voxel in voxels:
        foreground[voxel] = 1
    foreground_path = tmp_path / "foreground.nii.gz"
    skeleton_path = tmp_path / "skeleton.nii.gz"
    graph_path = tmp_path / "branch.graphml"
    _write_volume(foreground_path, foreground)
    _write_volume(skeleton_path, foreground)
    _write_graph(
        graph_path,
        node_positions=((2.0, 2.0, 2.0), (1.0, 2.0, 2.0), (3.0, 2.0, 2.0)),
        edge_paths=(((2, 2, 2),), ((2, 2, 2),)),
        edges=((0, 1), (0, 2)),
    )

    result = extract_features_from_paths(
        foreground_path, skeleton_path, graph_path, tmp_path / "edges.csv", tmp_path / "nodes.csv"
    )

    assert [(edge.node1_id, edge.node2_id) for edge in result.edges] == [(0, 1), (0, 2)]
    assert [(edge.node1_degree, edge.node2_degree) for edge in result.edges] == [(2, 1), (2, 1)]
    assert [(node.id, node.degree) for node in result.nodes] == [(0, 2), (1, 1), (2, 1)]
