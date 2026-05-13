# SkelHub Architecture

SkelHub is organized as four layers:

- I/O: load, validate, normalize, and write image data.
- Algorithms: backend-specific implementations isolated under `skelhub/algorithms/<name>/`.
- Evaluation: algorithm-agnostic consumers of shared framework results.
- CLI and orchestration: unified user-facing commands that route through the framework rather than backend-specific scripts.

Current implementation details:

- `skelhub.core.models` defines `VolumeData`, `SkeletonResult`, `GraphResult`, and `EvaluationResult`.
- `skelhub.core.registry` registers backends by algorithm name.
- `skelhub.api` is the framework orchestration layer that loads inputs, dispatches to a backend, writes outputs, and routes evaluation requests.
- `skelhub.evaluation` is intentionally separated into validation, geometry, morphology, reporting, and orchestration helpers so voxel-based evaluation stays decoupled from backend internals and graphification.
- `skelhub.visualization` contains the optional PyVista-based GraphML viewer used by `skelhub graphviz`.
- `skelhub.algorithms.mcp.backend` is the thin adapter that exposes the existing MCP implementation through the framework contract.
- `skelhub.algorithms.lee94.backend` is the thin adapter that exposes `scikit-image`'s Lee94 thinning implementation through the same framework contract.
- `skelhub.algorithms.laplacian.backend` adapts the VascGraph Laplacian graph-contraction path. It is graph-native internally, but returns a standard rasterized binary skeleton volume and stores the cleaned graph as optional metadata/output.
- `skelhub.algorithms.l1_skeleton.backend` adapts a Python-native L1-medial skeleton v2 path. It converts foreground voxels to point samples, contracts them with local density-aware L1 attraction and conditional repulsion, extracts branch curves for the default rasterized skeleton output, and keeps graph generation out of the backend contract.

Compatibility notes:

- The unified run path now supports multiple algorithms, including `mcp`, `lee94`, `laplacian`, and `l1_skeleton`, through the same registry-driven CLI and API route.
- The unified evaluation path currently operates on paired binary skeleton volumes and remains purely voxel-based; it does not depend on graph-generation code yet or backend-specific result internals.
- The evaluation modules are structured so a future `SkeletonResult` wrapper can reuse the same array-level evaluator rather than reimplementing metrics.
- The original top-level MCP modules remain in place for compatibility and traceability while the framework package becomes the primary path.
- Graph-native backends such as `laplacian` must adapt to `SkeletonResult.skeleton` by rasterizing their internal graph output; optional graph files remain backend extras rather than replacing the common volume contract.
