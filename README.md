# SkelHub

SkelHub is a Python framework for 3D skeletonization. It provides a shared package structure, a unified CLI, common result objects, and an algorithm-agnostic evaluation path so multiple skeletonization backends can live under one repo without turning the framework core into backend-specific glue.

Current status:

- Supported algorithm backends: `mcp`, `lee94`, `laplacian`, `l1_skeleton`
- Unified CLI entrypoints: `skelhub run`, `skelhub evaluate`, `skelhub graphgen`, `skelhub graphviz`
- Evaluation: working voxel-based v1 evaluation suite for binary 3D predicted/reference skeleton volumes
- Graph generation: Voreen-style skeleton NIfTI to proto-graph GraphML conversion
- Graph visualization: lightweight PyVista-based GraphML/NIfTI viewer for 3D vessel data

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

To use the built-in GraphML/NIfTI viewer:

```bash
# Initialze the viewer
python -m skelhub graphviz
# Initialize the viewer with a GraphML file
python -m skelhub graphviz --input ./test_data/lsys_graph/Lnet_i4_0_tort_centreline.graphml
# Initialize the viewer with a binary NIfTI file
python -m skelhub graphviz --input ./test_outputs/skelhub_mcp_small.nii.gz
```

If `skelhub` on your `PATH` comes from a different environment than the `python`/`pip` you used for installation, the graph viewer dependencies may still appear missing.

You can also install dependencies with `pip install -r requirements.txt`, but the console command `skelhub` is exposed through the package install.

## Repository Structure

```text
SkelHub/
├── docs/
├── skelhub/
│   ├── cli/
│   ├── core/
│   ├── io/
│   ├── algorithms/
│   │   ├── l1_skeleton/
│   │   ├── laplacian/
│   │   ├── lee94/
│   │   └── mcp/
│   ├── evaluation/
│   ├── preprocessing/
│   ├── postprocessing/
│   │   └── graphgen/
│   ├── visualization/
│   └── datasets/
├── tests/
└── test_data/
```

Framework notes:

- `skelhub.core` contains shared result objects, framework interfaces, and the backend registry.
- `skelhub.algorithms.mcp` contains the current MCP implementation and its thin framework adapter.
- `skelhub.algorithms.lee94` contains the Lee et al. 1994 thinning backend adapter around `scikit-image`.
- `skelhub.algorithms.laplacian` contains the VascGraph Laplacian graph-contraction backend, adapted to output a rasterized skeleton volume plus optional cleaned GraphML.
- `skelhub.algorithms.l1_skeleton` contains the Python-native L1-medial skeleton core v1 backend, adapted from point-cloud contraction to SkelHub's NIfTI volume contract.
- `skelhub.evaluation` contains the algorithm-agnostic voxel-based v1 evaluator, with separate validation, geometry, morphology, and reporting helpers.
- `skelhub.postprocessing.graphgen` contains [Voreen](https://github.com/voreen-project/voreen)-style skeleton-to-protograph GraphML generation.

## CLI Usage

Run MCP through the framework:

```bash
skelhub run \
  --algorithm mcp \
  --input ./test_data/small_test_data/CLIP_MASKED_sub_160um_seg.nii.gz \
  --output ./test_outputs/skelhub_mcp_small.nii.gz \
  --verbose
```

Equivalent local module execution without installation:

```bash
python -m skelhub run --algorithm mcp --input INPUT.nii.gz --output OUTPUT.nii.gz
```

Run Lee94 through the same framework path:

```bash
skelhub run \
  --algorithm lee94 \
  --input ./test_data/small_test_data/CLIP_MASKED_sub_160um_seg.nii.gz \
  --output ./test_outputs/skelhub_lee94_small.nii.gz \
  --verbose
```

Run the VascGraph Laplacian backend:

```bash
skelhub run \
  --algorithm laplacian \
  --input ./test_data/lsys_data/iter_4_8_step_1/Lnet_i4_0_tort.nii.gz \
  --output ./test_outputs/skelhub_laplacian.nii.gz \
  --verbose
```

Optionally add `--graph_output ./test_outputs/skelhub_laplacian.graphml` to export the cleaned graph. Add `--graph_original ./test_outputs/skelhub_laplacian_original.graphml` to export the refined graph before `post_node_cleaning()`. (NOTE: output graph is only available for this one, as the original work was based on dense graph and no intermediate rasterized output could be used as skeleton. Here I added a rasterized skeleton built upon the cleaned graph)

Run the Python-native L1-medial skeleton backend:

```bash
skelhub run \
  --algorithm l1_skeleton \
  --input ./test_data/small_test_data/CLIP_MASKED_sub_160um_seg.nii.gz \
  --output ./test_outputs/skelhub_l1_skeleton_small.nii.gz \
  --verbose
```

MCP parameters exposed at the framework level:

- `--root-method {max_fdt,topmost}`
- `--threshold-scale FLOAT`
- `--dilation-factor FLOAT`
- `--max-iterations INT`
- `--min-object-size INT`
- `--label-objects`
- `--verbose`

Lee94 parameters exposed at the framework level:

- `--binarize-threshold FLOAT`

Laplacian parameters exposed at the framework level:

- `--graph_output PATH` optional cleaned GraphML output path
- `--graph_original PATH` optional refined pre-cleaning GraphML output path
- `--speed_param FLOAT` default `0.05`
- `--dist_param FLOAT` default `0.5`
- `--med_param FLOAT` default `0.5`
- `--degree_threshold FLOAT` default `5.0`
- `--sampling FLOAT` default `1.0`
- `--clustering_r FLOAT` default `1.0`
- `--stop_param FLOAT` default `0.001`
- `--n_free_iteration INT` default `0`
- `--area_param FLOAT` default `50.0`
- `--poly_param INT` default `10`

L1 skeleton parameters exposed at the framework level:

- `--l1-sample-count INT` default `512`
- `--l1-initial-radius FLOAT` optional, auto-estimated from foreground point spacing when omitted
- `--l1-radius-growth FLOAT` default `1.5`
- `--l1-max-radius FLOAT` optional, auto-estimated from foreground extent when omitted
- `--l1-max-iterations INT` default `80`
- `--l1-stop-error FLOAT` default `0.01`
- `--l1-repulsion-mu FLOAT` default `0.35`
- `--l1-repulsion-mu-min FLOAT` default `0.15`
- `--l1-random-seed INT` default `0`

Run the voxel-based evaluation suite:

```bash
skelhub evaluate \
  --pred ./test_outputs/skelhub_mcp_small.nii.gz \
  --ref ./test_data/lsys_gt/reference_skeleton.nii.gz \
  --buffer-radius 1 \
  --buffer-radius-unit voxels
```

Optional evaluation flags:

- `-b, --buffer-radius FLOAT` required buffer dilation radius
- `--buffer-radius-unit {voxels,um}` optional radius unit, default `voxels`
- `--json-output PATH` optional structured JSON report output
- `-v, --verbose` optional progress logs and detailed terminal report

Generate a Voreen-style proto-graph GraphML file from a skeleton NIfTI:

```bash
skelhub graphgen \
  --input ./test_data/lsys_gt/iter_4_8_step_1/Lnet_i4_0_tort_centreline_26conn.nii.gz \
  --output ./test_outputs/lsys.graphml \
  --verbose
```

Open a GraphML vessel graph or binary NIfTI volume in the interactive PyVista viewer:

```bash
skelhub graphviz

skelhub graphviz \
  --input ./test_data/lsys_graph/Lnet_i4_0_tort_centreline.graphml \
  --edge_thickness 2.5 \
  --node_size 7

skelhub graphviz \
  --input ./test_outputs/skelhub_mcp_small.nii.gz
```

The graph viewer expects per-node spatial metadata. SkelHub's current GraphML export writes node coordinates as `X`, `Y`, and `Z`, and the viewer uses those fields directly.
For NIfTI inputs, the viewer requires a 3D binary volume with values exactly in `{0, 1}` and renders each foreground voxel as one unit block in voxel-index coordinates.

### Note:
When deploy on HPC (e.g., Bunya), it's necessary to use conda environment then install/update conda C++ runtime:

```bash
conda activate your_env
conda install -c conda-forge libstdcxx-ng
skelhub graphviz 
```

Safer option:
```bash
module unload Miniconda3
module load Miniconda3
conda activate your_env
conda install -c conda-forge libstdcxx-ng
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
skelhub graphviz 
```

## Python API

```python
from skelhub.api import (
    evaluate_prediction_path,
    generate_graphml_from_skeleton_path,
    run_algorithm_from_path,
)
from skelhub.algorithms import L1SkeletonConfig, LaplacianConfig, Lee94Config, MCPConfig

result = run_algorithm_from_path(
    algorithm="lee94",
    input_path="input.nii.gz",
    output_path="out.nii.gz",
    config=Lee94Config(binarize_threshold=0.5),
)

evaluation = evaluate_prediction_path(
    "pred.nii.gz",
    "ref.nii.gz",
    buffer_radius=1.0,
    buffer_radius_unit="voxels",
)
graph = generate_graphml_from_skeleton_path("pred.nii.gz", "pred.graphml")
laplacian = run_algorithm_from_path(
    algorithm="laplacian",
    input_path="input.nii.gz",
    output_path="laplacian.nii.gz",
    config=LaplacianConfig(graph_output="laplacian.graphml"),
)
print(result.backend_metadata["config"])
print(evaluation.P)
print(len(graph.nodes), len(graph.edges))
```

## Outputs

`SkeletonResult` is the framework-level output container for all backends. It stores:

- `algorithm_name`
- `skeleton` voxel array
- `input_metadata`
- `runtime_stats`
- `warnings`
- `backend_metadata`
- optional `graph`

The MCP backend keeps its current per-object runtime metadata under `result.backend_metadata["mcp"]`.
The Lee94 backend records its wrapper metadata under `result.backend_metadata["lee94"]` and uses `scikit-image`'s Lee-method implementation rather than a custom in-repo thinning implementation.
The Laplacian backend records graph-contraction metadata under `result.backend_metadata["laplacian"]`, including cleaned graph node/edge counts and the rasterized skeleton voxel count.

`EvaluationResult` now records the v1 evaluation outputs explicitly, including:

- `TP`, `FP`, `FN`
- `Cp`, `Cr`
- raw, clipped, and normalized morphology values for `OCC`, `BCC`, and `E`
- global performance score `P`
- buffer radius metadata
- connectivity metadata
- warnings

## Graph Visualization

`skelhub graphviz` opens a lightweight PyVista viewer for GraphML vessel graphs and binary NIfTI volumes. The viewer:

- loads GraphML through the existing `igraph` dependency
- loads NIfTI through the existing `nibabel` dependency
- renders nodes and edges in 3D with simple constant-size geometry
- renders binary NIfTI foreground voxels as unit 3D blocks
- uses PyVista's built-in mouse controls for camera interaction
- accepts GraphML appearance controls through `--edge_thickness` and `--node_size`
- opens an empty PyVista window if `--input` is omitted
- can load multiple GraphML and NIfTI files in one session while displaying one active file at a time
- provides a right-aligned in-canvas command row with fixed-size button backgrounds for `Import`, `Close`, `<`, `>`, red `Refresh`, and blue `Reset View`
- previews node-size and edge-thickness slider values for active GraphML files, then applies them when `Refresh` is pressed
- hides the node-size and edge-thickness sliders for active NIfTI files while keeping the command buttons visible
- restores the active graph's initial camera view with `Reset View` without changing loaded files or slider values
- unfolds the loaded-file list when the mouse hovers over the compact top-left file label
- accepts `.graphml`, `.nii`, and `.nii.gz` drag-and-drop events when the desktop VTK/PyVista backend exposes file drops to the render window

If the GraphML file does not contain usable node coordinates, the command fails clearly instead of guessing layout data.
If a NIfTI file is not exactly binary, the viewer shows a warning and rejects the import.

## Evaluation Overview

The current evaluation subsystem is a real but intentionally conservative v1 implementation. It:

- evaluates two binary 3D skeleton volumes: predicted and reference
- fails hard on mismatched shape, mismatched spacing, or non-binary values
- computes geometry preservation with the buffer method
- computes 3D morphology quality from connected components and voxel endpoints
- reports a global quality-style score `P`
- stays voxel-based and algorithm-agnostic

The v1 metrics are:

- Geometry preservation: `TP`, `FP`, `FN`, completeness `Cp`, and correctness `Cr`
- Morphology quality: raw signed `OCC`, `BCC`, and `E`, plus clipped and normalized quality variants
- Global score: `P = mean(Cp, Cr, OCC_normalized, BCC_normalized, E_normalized)`

Current limitations:

- 3D only
- raw binary skeleton inputs only
- voxel-based only
- not graph-based
- not yet exposed primarily through `SkeletonResult` objects, though the array-level evaluator is structured to make that extension straightforward

## Documentation

- [Architecture](docs/architecture.md)
- [Algorithms](docs/algorithms.md)
- [Evaluation](docs/evaluation.md)
