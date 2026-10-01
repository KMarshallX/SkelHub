# Python API

Use the Python API when you want SkelHub inside scripts, notebooks, or workflow runners.

For CLI examples, see:

- [Algorithms](algorithms.md)
- [Evaluation](evaluation.md)
- [Visualization](visualization.md)

## Main Entry Points

```python
from skelhub.api import (
    evaluate_prediction_path,
    extract_features_from_paths,
    generate_graphml_from_skeleton_path,
    launch_graph_viewer_from_path,
    run_algorithm_from_path,
)
```

Backend config objects live in `skelhub.algorithms`:

```python
from skelhub.algorithms import (
    FluxConfig,
    L1SkeletonConfig,
    LaplacianConfig,
    Lee94Config,
    MCPConfig,
    PalagyiKubaConfig,
)
```

## Run an Algorithm

```python
from skelhub.api import run_algorithm_from_path
from skelhub.algorithms import LaplacianConfig

result = run_algorithm_from_path(
    algorithm="laplacian",
    input_path="input.nii.gz",
    output_path="laplacian.nii.gz",
    config=LaplacianConfig(graph_output="laplacian.graphml"),
)

print(result.algorithm_name)
print(result.backend_metadata["laplacian"])
```

Other backend configs follow the same pattern:

```python
from skelhub.algorithms import Lee94Config, MCPConfig, PalagyiKubaConfig

lee94 = Lee94Config(binarize_threshold=0.5)
mcp = MCPConfig(root_method="max_fdt", min_object_size=50)
pk = PalagyiKubaConfig(mode="curve")
```

## Evaluate a Prediction

```python
from skelhub.api import evaluate_prediction_path

evaluation = evaluate_prediction_path(
    "pred.nii.gz",
    "ref.nii.gz",
    buffer_radius=[50, 100],  # first value is the primary tolerance
    buffer_radius_unit="um",
)

print(evaluation.status)                          # "ok", "empty_prediction", ...
print(evaluation.geometry.primary.f1)
print(evaluation.geometry.distances.symmetric_p95_um)
print(evaluation.topology.comparison(1))          # cycles, reference vs prediction
```

To evaluate a backend result directly, pass the `VolumeData` it ran on as the prediction grid:

```python
from skelhub.api import evaluate_skeleton_result

evaluation = evaluate_skeleton_result(result, reference_volume, input_volume=volume, buffer_radius=[1, 2])
```

If a NIfTI header's unit is `unknown`, declare it with `pred_spatial_unit="mm"` / `ref_spatial_unit="mm"` (also accepted by `evaluate_skeleton_result`). A declaration cannot override a known header unit.

There is no combined score. See [Evaluation](evaluation.md) for formulas and input rules.

## Generate GraphML

```python
from skelhub.api import generate_graphml_from_skeleton_path

graph = generate_graphml_from_skeleton_path(
    "pred.nii.gz",
    "pred.graphml",
)

print(len(graph.nodes), len(graph.edges))
```

## Extract Vessel Features

```python
from skelhub.api import extract_features_from_paths

features = extract_features_from_paths(
    "vessels.nii.gz",
    "skeleton.nii.gz",
    "vessel.graphml",
    "edge_features.csv",
    "node_features.csv",
)

print(len(features.edges), features.physical_unit)
```

The GraphML input may be created by `skelhub graphgen` or by
`skelhub run --algorithm laplacian --graph_output ...`. Edge CSV base
measurements are in voxel units. Additional `*_image_<unit>` columns use the
foreground NIfTI header voxel sizes and spatial unit.
The node CSV exports voxel-space positions and graph incidence degree.

## Launch Visualization

```python
from skelhub.api import launch_graph_viewer_from_path

launch_graph_viewer_from_path(
    "pred.graphml",
    edge_thickness=1.0,
    node_size=2.5,
    edge_geometry="continuous",
)
```

`edge_geometry` accepts `"straight"` (default), `"continuous"`, or
`"voxel"`. Curved modes require compatible GraphML voxel-path attributes and
node voxel/world coordinate pairs.

For result fields, see [Structured Output](StructuredOutput.md).
