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
- `skelhub.visualization` contains the optional PySide6-based GraphML viewer used by `skelhub graphviz`.
- `skelhub.algorithms.mcp.backend` is the thin adapter that exposes the existing MCP implementation through the framework contract.
- `skelhub.algorithms.lee94.backend` is the thin adapter that exposes `scikit-image`'s Lee94 thinning implementation through the same framework contract.

Compatibility notes:

- The unified run path now supports multiple algorithms, including `mcp` and `lee94`, through the same registry-driven CLI and API route.
- The unified evaluation path currently operates on paired binary skeleton volumes and remains purely voxel-based; it does not depend on graph-generation code yet or backend-specific result internals.
- The evaluation modules are structured so a future `SkeletonResult` wrapper can reuse the same array-level evaluator rather than reimplementing metrics.
- The original top-level MCP modules remain in place for compatibility and traceability while the framework package becomes the primary path.
