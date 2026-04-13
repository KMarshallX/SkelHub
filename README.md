# SkelHub

SkelHub is a Python framework for 3D skeletonization. It provides a shared package structure, a unified CLI, common result objects, and an algorithm-agnostic evaluation path so multiple skeletonization backends can live under one repo without turning the framework core into backend-specific glue.

Current status:

- Supported algorithm backends: `mcp`
- Unified CLI entrypoints: `skelhub run`, `skelhub evaluate`
- Evaluation: placeholder path that validates and loads skeleton NIfTI predictions

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

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
│   │   └── mcp/
│   ├── evaluation/
│   ├── preprocessing/
│   ├── postprocessing/
│   ├── visualization/
│   └── datasets/
├── tests/
└── test_data/
```

Framework notes:

- `skelhub.core` contains shared result objects, framework interfaces, and the backend registry.
- `skelhub.algorithms.mcp` contains the current MCP implementation and its thin framework adapter.
- `skelhub.evaluation` currently contains a placeholder evaluator that validates and loads a skeleton NIfTI through the framework path.

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

MCP parameters exposed at the framework level:

- `--root-method {max_fdt,topmost}`
- `--threshold-scale FLOAT`
- `--dilation-factor FLOAT`
- `--max-iterations INT`
- `--min-object-size INT`
- `--label-objects`
- `--verbose`

Run the evaluation placeholder:

```bash
skelhub evaluate --pred ./test_outputs/skelhub_mcp_small.nii.gz
```

## Python API

```python
from skelhub.api import evaluate_prediction_path, run_algorithm_from_path
from skelhub.algorithms.mcp import MCPConfig

result = run_algorithm_from_path(
    algorithm="mcp",
    input_path="input.nii.gz",
    output_path="out.nii.gz",
    config=MCPConfig(min_object_size=50),
)

evaluation = evaluate_prediction_path("out.nii.gz")
print(result.backend_metadata["config"])
print(evaluation.message)
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

## Evaluation Overview

The current evaluation subsystem is intentionally minimal. It:

- accepts a skeleton prediction path in `.nii` or `.nii.gz`
- validates the path and loads the NIfTI correctly
- runs through a framework-level evaluation function
- emits a clear placeholder success message

Metric computation is intentionally deferred until the common framework interfaces settle.

## Documentation

- [Architecture](docs/architecture.md)
- [Algorithms](docs/algorithms.md)
- [Evaluation](docs/evaluation.md)
- [Development Log](LOG.md)
