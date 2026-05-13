"""Laplacian backend tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import igraph as ig
import nibabel as nib
import numpy as np

from skelhub.algorithms.laplacian import LaplacianConfig
from skelhub.algorithms.laplacian.graph import GeometricGraph
from skelhub.algorithms.laplacian.graphml import write_laplacian_graphml
from skelhub.algorithms.laplacian.rasterize import rasterize_graph_26conn
from skelhub.core import SkeletonResult, VolumeData, get_backend, list_backends


REPO_ROOT = Path(__file__).resolve().parents[1]


def _tiny_tube() -> np.ndarray:
    volume = np.zeros((7, 7, 7), dtype=np.float32)
    volume[3, 3, 1:6] = 1.0
    return volume


def test_registry_exposes_laplacian_backend() -> None:
    assert "laplacian" in list_backends()
    assert get_backend("laplacian").name == "laplacian"


def test_laplacian_config_defaults_match_demo() -> None:
    config = LaplacianConfig().validate()

    assert config.speed_param == 0.05
    assert config.dist_param == 0.5
    assert config.med_param == 0.5
    assert config.degree_threshold == 5.0
    assert config.sampling == 1.0
    assert config.clustering_r == 1.0
    assert config.stop_param == 0.001
    assert config.n_free_iteration == 0
    assert config.area_param == 50.0
    assert config.poly_param == 10


def test_laplacian_config_validation_rejects_bad_values() -> None:
    try:
        LaplacianConfig(speed_param=0.0).validate()
    except ValueError:
        pass
    else:
        raise AssertionError("Expected LaplacianConfig to reject non-positive speed_param.")


def test_laplacian_backend_returns_rasterized_skeleton() -> None:
    data = _tiny_tube()
    volume = VolumeData(
        data=data,
        affine=np.eye(4),
        header=None,
        path="memory",
        spacing=(1.0, 1.0, 1.0),
    )

    result = get_backend("laplacian").run(volume=volume, config=LaplacianConfig())

    assert isinstance(result, SkeletonResult)
    assert result.algorithm_name == "laplacian"
    assert result.skeleton.shape == data.shape
    assert set(np.unique(result.skeleton)).issubset({0, 1})
    assert np.count_nonzero(result.skeleton) > 0
    metadata = result.backend_metadata["laplacian"]
    assert metadata["cleaned_nodes"] > 0
    assert metadata["cleaned_edges"] > 0
    assert metadata["output_foreground_voxels"] == int(np.count_nonzero(result.skeleton))


def test_rasterize_graph_edges_are_26_connected() -> None:
    graph = GeometricGraph(nodes_pos=[(0, 0, 0), (3, 3, 3)], edges=[(0, 1)])

    skeleton = rasterize_graph_26conn(graph, shape=(4, 4, 4))
    voxels = np.argwhere(skeleton > 0)
    ordered = voxels[np.argsort(voxels[:, 0])]

    assert int(np.count_nonzero(skeleton)) == 4
    assert tuple(ordered[0]) == (0, 0, 0)
    assert tuple(ordered[-1]) == (3, 3, 3)
    diffs = np.abs(np.diff(ordered, axis=0))
    assert np.all(diffs <= 1)


def test_laplacian_graphml_export_uses_world_coordinates(tmp_path: Path) -> None:
    graph = GeometricGraph(nodes_pos=[(1, 1, 1), (2, 2, 2)], edges=[(0, 1)])
    output_path = tmp_path / "laplacian.graphml"
    affine = np.diag([2.0, 3.0, 4.0, 1.0])

    write_laplacian_graphml(graph, output_path, affine=affine, shape=(4, 4, 4))
    loaded = ig.Graph.Read_GraphML(str(output_path))

    assert output_path.exists()
    assert loaded.vcount() == 2
    assert loaded.ecount() == 1
    assert all(np.isfinite(float(value)) for value in loaded.vs["X"])
    assert loaded.vs["X"][0] == 2.0
    assert loaded.vs["Y"][0] == 3.0
    assert loaded.vs["Z"][0] == 4.0
    assert "voxel_pos" in loaded.vs.attributes()
    assert "centerline_voxels" in loaded.es.attributes()


def test_framework_run_cli_lists_laplacian_choice() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "skelhub", "run", "--help"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert "laplacian" in result.stdout
    assert "--graph_output" in result.stdout


def test_framework_run_cli_executes_laplacian_and_writes_graphml(tmp_path: Path) -> None:
    input_path = tmp_path / "input.nii.gz"
    output_path = tmp_path / "out.nii.gz"
    graph_path = tmp_path / "out.graphml"
    nib.save(nib.Nifti1Image(_tiny_tube(), affine=np.eye(4)), str(input_path))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "skelhub",
            "run",
            "--algorithm",
            "laplacian",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--graph_output",
            str(graph_path),
            "--verbose",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    out = np.asarray(nib.load(str(output_path)).dataobj)
    loaded_graph = ig.Graph.Read_GraphML(str(graph_path))
    assert output_path.exists()
    assert graph_path.exists()
    assert np.count_nonzero(out) > 0
    assert loaded_graph.vcount() > 0
    assert loaded_graph.ecount() > 0
    assert "framework run complete: algorithm=laplacian" in result.stdout
