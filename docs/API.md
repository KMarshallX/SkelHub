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
    buffer_radius=1.0,
    buffer_radius_unit="voxels",
)

print(evaluation.Cp)
print(evaluation.Cr)
print(evaluation.P)
```

## Generate GraphML

```python
from skelhub.api import generate_graphml_from_skeleton_path

graph = generate_graphml_from_skeleton_path(
    "pred.nii.gz",
    "pred.graphml",
)

print(len(graph.nodes), len(graph.edges))
```

## Launch Visualization

```python
from skelhub.api import launch_graph_viewer_from_path

launch_graph_viewer_from_path(
    "pred.graphml",
    edge_thickness=2.0,
    node_size=6.0,
)
```

For result fields, see [Structured Output](StructuredOutput.md).
