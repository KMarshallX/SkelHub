"""Tests for Voreen-faithful skeleton-to-protograph generation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import igraph as ig
import numpy as np

from skelhub.postprocessing.graphgen import (
    classify_skeleton_voxels,
    generate_protograph_from_skeleton,
)
from skelhub.postprocessing.graphgen.classification import BRANCH, END, REGULAR
from skelhub.postprocessing.graphgen.components import SkeletonComponents
from skelhub.postprocessing.graphgen.graphml import write_graphml
from skelhub.postprocessing.graphgen.protograph import build_protograph


REPO_ROOT = Path(__file__).resolve().parents[1]
LSYS_CENTERLINE = (
    REPO_ROOT
    / "test_data"
    / "lsys_gt"
    / "iter_4_8_step_1"
    / "Lnet_i4_0_tort_centreline_26conn.nii.gz"
)


def test_classification_matches_voreen_neighbor_count_rules() -> None:
    skeleton = np.zeros((7, 7, 7), dtype=np.uint8)
    skeleton[1:6, 3, 3] = 1

    classes = classify_skeleton_voxels(skeleton)

    assert classes[0, 0, 0] == 0
    assert classes[1, 3, 3] == END
    assert classes[5, 3, 3] == END
    assert classes[2, 3, 3] == REGULAR

    skeleton[3, 4, 3] = 1
    classes = classify_skeleton_voxels(skeleton)
    assert classes[3, 3, 3] == BRANCH


def test_straight_chain_becomes_two_endpoint_nodes_and_one_edge() -> None:
    skeleton = np.zeros((7, 7, 7), dtype=np.uint8)
    skeleton[1:6, 3, 3] = 1

    graph = generate_protograph_from_skeleton(skeleton, affine=np.eye(4))

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert {node.kind for node in graph.nodes} == {"endpoint"}
    assert graph.edges[0].node1 != graph.edges[0].node2
    assert graph.edges[0].voxels == [(2, 3, 3), (3, 3, 3), (4, 3, 3)]


def test_branch_pattern_creates_branch_node_and_incident_edges() -> None:
    skeleton = np.zeros((9, 9, 9), dtype=np.uint8)
    skeleton[1:8, 4, 4] = 1
    skeleton[4, 4, 5:8] = 1

    graph = generate_protograph_from_skeleton(skeleton, affine=np.eye(4))

    assert any(node.kind == "branch" for node in graph.nodes)
    assert len([node for node in graph.nodes if node.kind == "endpoint"]) >= 3
    assert len(graph.edges) >= 3


def test_freestanding_regular_loop_creates_synthetic_loop_node() -> None:
    components = SkeletonComponents(
        endpoints=[],
        branch_components=[],
        regular_components=[
            [
                (1, 1, 1),
                (2, 1, 1),
                (3, 2, 1),
                (3, 3, 2),
                (2, 3, 3),
                (1, 2, 2),
            ]
        ],
    )

    graph = build_protograph(components, shape=(5, 5, 5), affine=np.eye(4))

    assert len(graph.nodes) == 1
    assert graph.nodes[0].kind == "synthetic_loop"
    assert len(graph.edges) == 1
    assert graph.edges[0].node1 == graph.edges[0].node2 == graph.nodes[0].id
    assert graph.edges[0].voxels


def test_graphml_export_has_nodes_edges_and_coordinates(tmp_path: Path) -> None:
    skeleton = np.zeros((7, 7, 7), dtype=np.uint8)
    skeleton[1:6, 3, 3] = 1
    graph = generate_protograph_from_skeleton(skeleton, affine=np.eye(4))
    output_path = tmp_path / "chain.graphml"

    write_graphml(graph, output_path)
    loaded = ig.Graph.Read_GraphML(str(output_path))

    assert loaded.vcount() == 2
    assert loaded.ecount() == 1
    assert all(float(value) >= 0.0 for value in loaded.vs["X"])
    assert "voxels" in loaded.vs.attributes()
    assert "centerline_voxels" in loaded.es.attributes()


def test_graphgen_cli_writes_nonempty_graphml_for_lsys_centerline(tmp_path: Path) -> None:
    output_path = tmp_path / "lsys.graphml"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "skelhub",
            "graphgen",
            "-i",
            str(LSYS_CENTERLINE),
            "-o",
            str(output_path),
            "--verbose",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    loaded = ig.Graph.Read_GraphML(str(output_path))
    assert output_path.exists()
    assert loaded.vcount() > 0
    assert loaded.ecount() > 0
    assert all(np.isfinite(float(value)) for value in loaded.vs["X"])
    assert "graphgen complete" in result.stdout
