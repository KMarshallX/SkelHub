# SkelHub

SkelHub is a Python framework for 3D skeletonization. It provides a shared package structure, a unified CLI, common result objects, and an algorithm-agnostic evaluation path so multiple skeletonization backends can live under one repo without turning the framework core into backend-specific glue.

Current status:

- Supported algorithm backends: `mcp`, `lee94`
- Unified CLI entrypoints: `skelhub run`, `skelhub evaluate`, `skelhub graphgen`, `skelhub graphviz`
- Evaluation: working voxel-based v1 evaluation suite for binary 3D predicted/reference skeleton volumes
- Graph generation: Voreen-style skeleton NIfTI to proto-graph GraphML conversion
- Graph visualization: optional PySide6-based GraphML viewer for 3D vessel graphs

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

To use the built-in GraphML viewer: 

*Note: the visualizing module has a known bug - you have to hit the **Rebuild** button around 3 times to render the complete graph*

```bash
# Initialze the viewer
python -m skelhub graphviz
# Initialize the viewer with a GraphML file
python -m skelhub graphviz --input ./test_data/lsys_graph/Lnet_i4_0_tort_centreline.graphml
# Troubleshooting mode
SKELHUB_GRAPH_VIEWER_TROUBLESHOOT=1 python -m skelhub graphviz --input ./test_data/lsys_graph/Lnet_i4_0_tort_centreline.graphml
```

If `skelhub` on your `PATH` comes from a different environment than the `python`/`pip` you used for installation, the graph viewer extras may still appear missing.

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

Open a GraphML vessel graph in the interactive PySide6 viewer:

```bash
skelhub graphviz

skelhub graphviz \
  --input ./test_data/lsys_graph/Lnet_i4_0_tort_centreline.graphml \
  --edge_thickness 2.5 \
  --node_size 7
```

The graph viewer expects per-node spatial metadata. SkelHub's current GraphML export writes node coordinates as `X`, `Y`, and `Z`, and the viewer uses those fields directly.

## Python API

```python
from skelhub.api import (
    evaluate_prediction_path,
    generate_graphml_from_skeleton_path,
    run_algorithm_from_path,
)
from skelhub.algorithms import Lee94Config, MCPConfig

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

`EvaluationResult` now records the v1 evaluation outputs explicitly, including:

- `TP`, `FP`, `FN`
- `Cp`, `Cr`
- raw, clipped, and normalized morphology values for `OCC`, `BCC`, and `E`
- global performance score `P`
- buffer radius metadata
- connectivity metadata
- warnings

## Graph Visualization

`skelhub graphviz` opens a lightweight PySide6 Qt3D viewer for GraphML vessel graphs. The viewer:

- loads GraphML through the existing `igraph` dependency
- renders nodes and edges in 3D
- supports mouse dragging for camera rotation
- supports the mouse wheel for zooming
- opens with a toolbar-based `File` menu for loading, unloading, and switching between GraphML files in the current session
- accepts appearance controls through `--edge_thickness` and `--node_size`
- includes a toolbar-toggled right-side appearance panel for real-time node size, edge thickness, and panel opacity adjustment

When the viewer is launched from the CLI with `--input`, that GraphML file is loaded as the initial active file in the `File` menu. If `--input` is omitted, the viewer opens in a clean empty state and files can be loaded from the toolbar. Additional GraphML files can then be loaded from the toolbar, and unloading the last remaining file returns the window to a clean empty state instead of closing or crashing.

Compared with the previous `pyqtgraph` implementation, node and edge sizing is now applied in scene units inside Qt3D rather than pixel-space OpenGL primitives. The CLI flags and their overall purpose stay the same, but exact apparent thickness can vary a little with camera distance and graph scale.
The appearance panel maps edge thickness to the same rendered Qt line-width interval used by the backend, currently `2.0` to `10.0`.

If the GraphML file does not contain usable node coordinates, the command fails clearly instead of guessing layout data.

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
