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
- `skelhub.algorithms.mcp.backend` is the thin adapter that exposes the existing MCP implementation through the framework contract.

Compatibility notes:

- The legacy top-level `main.py` is retained as a non-destructive wrapper, but it now forwards execution into the framework CLI as `skelhub run --algorithm mcp`.
- The original top-level MCP modules remain in place for compatibility and traceability while the framework package becomes the primary path.
