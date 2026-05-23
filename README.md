# SkelHub

SkelHub is a Python framework for **3D skeletonization**.

It brings several skeletonization methods into one package, with:

- one shared CLI
- one backend registry
- common result objects
- algorithm-agnostic evaluation
- optional graph generation and visualization tools

The goal is simple: keep each algorithm backend isolated, while giving users one clean way to run, compare, and inspect skeleton outputs.

## Overview

Current status:

- Supported backends: `laplacian`, `mcp`, `lee94`, `l1_skeleton`, `palagyi_kuba`, `flux`
- CLI entrypoints: `skelhub run`, `skelhub evaluate`, `skelhub graphgen`, `skelhub graphviz`
- Evaluation: voxel-based v1 metrics for paired 3D binary skeleton volumes
- Visualization: PyVista-based viewer for GraphML graphs and binary NIfTI volumes

SkelHub is organized around four layers:

- **I/O:** read, validate, normalize, and write volumes.
- **Algorithms:** run isolated backend implementations.
- **Evaluation:** compare standardized skeleton outputs.
- **CLI/API:** provide stable user-facing entrypoints.

## Installation

### Conda environment

**Recommended** for HPC and desktop environments that need the graph viewer.

```bash
conda create -n skelhub python=3.11
conda activate skelhub
python -m pip install -e .
```

For the PyVista graph viewer, some HPC systems need an updated C++ runtime:

```bash
conda install -c conda-forge libstdcxx-ng
```

If the viewer still reports runtime library issues, prefer a clean module stack:

```bash
module unload Miniconda3
module load Miniconda3
conda activate skelhub
conda install -c conda-forge libstdcxx-ng
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
```

### Python venv

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

You can also install dependencies with:

```bash
python -m pip install -r requirements.txt
```

The console command `skelhub` is exposed by the package install. If `skelhub` points to a different environment than `python`, use:

```bash
python -m skelhub --help
```

## CLI Usage

Use the focused docs below:

- [Algorithms](docs/algorithms.md)
- [Evaluation](docs/evaluation.md)
- [Visualization](docs/visualization.md)
- [Python API](docs/API.md)

## Repository Structure

```text
SkelHub/
├── docs/
│   ├── API.md
│   ├── StructuredOutput.md
│   ├── algorithms.md
│   ├── architecture.md
│   ├── evaluation.md
│   └── visualization.md
├── skelhub/
│   ├── cli/
│   ├── core/
│   ├── io/
│   ├── algorithms/
│   │   ├── laplacian/
│   │   ├── mcp/
│   │   ├── lee94/
│   │   ├── l1_skeleton/
│   │   ├── palagyi_kuba/
│   │   └── flux/
│   ├── evaluation/
│   ├── preprocessing/
│   ├── postprocessing/
│   │   └── graphgen/
│   ├── visualization/
│   └── datasets/
├── tests/
└── pyproject.toml
```

Key locations:

- `skelhub.core` defines shared data models, interfaces, and the backend registry.
- `skelhub.algorithms` contains isolated backend adapters and implementations.
- `skelhub.evaluation` contains the voxel-based evaluator.
- `skelhub.postprocessing.graphgen` converts skeleton NIfTI volumes into GraphML.
- `skelhub.visualization` powers `skelhub graphviz`.

## Structured Output

SkelHub uses typed result containers for skeletons, graphs, and evaluation reports. See [Structured Output](docs/StructuredOutput.md) for the current contract.

*Review pending:* this output structure is stable enough to use, but it will be reviewed as the framework matures.
