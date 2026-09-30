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
- `skelhub.visualization` contains the optional PyVista-based GraphML/NIfTI viewer used by `skelhub graphviz`. Graph nodes and optional edge paths are normalized into world-space viewer data during loading, while rendering remains independent of GraphML backend details. Its legacy `graph_viewer` import path is kept as a compatibility facade, while focused modules group constants, typed models, loading, session state, scene rendering, layout, camera behavior, controls, interaction, and launcher entrypoints.
- `skelhub.gui` is an optional PySide6 desktop layer for Graph Tools. It calls reusable postprocessing services and keeps topology analysis, graphgen caching, and report writing separate from widgets. `skelhub gui` loads the optional dependencies only at launch. It is under active development and separate from `skelhub graphviz`; see [GUI](GUI.md).
- The EDT Heat tab is split across the layers:
  - I/O: `skelhub.io.nifti_reader.read_binary_mask` (strict binary 3D NIfTI) and `skelhub.io.graphml_reader` (`voxel_pos`, `centerline_voxel_points`, optional world coordinates). The viewer's GraphML point/path parsers and node-ID rule now come from `graphml_reader`, under their old private names.
  - Evaluation: `skelhub.evaluation.centeredness` computes the local EDT ratio from a precomputed EDT and component labels. It has no Qt, VTK, file, or backend code, and offers a `SkeletonResult` adapter.
  - Processing: `skelhub.postprocessing.edt` validates alignment and samples the chosen distance, or passes Voxel EDT samples to the centeredness kernel for the local EDT ratio. Distances: the physical voxel EDT, or (GraphML only) the distance to the marching-cubes 0.5 surface from `skelhub.postprocessing.surface_distance`. The surface module uses VTK only as a geometry library (closest-point locator and inside test), with no rendering. No Qt, no algorithm backend. It shares `points_in_foreground_cells` with the checker.
  - Visualization: `skelhub.visualization.heatmap` (colour bands, gradient, legend data, optional fixed value range) and `skelhub.visualization.edt_heat` (actors, in-place recolouring, picking) work on any PyVista plotter.
  - GUI: `skelhub.gui.edt_tab` owns the widgets (Colour by, distance method, and α selectors), the lazily created `pyvistaqt.QtInteractor`, the per-settings result cache, the surface cache, and stale-result handling. It runs calculations through the window's existing background worker.
- `skelhub.algorithms.mcp.backend` is the thin adapter that exposes the existing MCP implementation through the framework contract.
- `skelhub.algorithms.lee94.backend` is the thin adapter that exposes `scikit-image`'s Lee94 thinning implementation through the same framework contract.
- `skelhub.algorithms.laplacian.backend` adapts the VascGraph Laplacian graph-contraction path. It is graph-native internally, but returns a standard rasterized binary skeleton volume and stores the cleaned graph as optional metadata/output.
- `skelhub.algorithms.l1_skeleton.backend` adapts a Python-native L1-medial skeleton v2 path. It converts foreground voxels to point samples, contracts them with local density-aware L1 attraction and conditional repulsion, extracts branch curves for the default rasterized skeleton output, and keeps graph generation out of the backend contract.
- `skelhub.postprocessing.protograph_cleaner` performs geometry-preserving
  degree-2 chain contraction independently of the Laplacian backend. The shell
  entrypoint remains orchestration-only, while GraphML validation, path
  concatenation, multiedge preservation, and writing stay in postprocessing.

Compatibility notes:

- The unified run path now supports multiple algorithms, including `mcp`, `lee94`, `laplacian`, and `l1_skeleton`, through the same registry-driven CLI and API route.
- The unified evaluation path currently operates on paired binary skeleton volumes and remains purely voxel-based; it does not depend on graph-generation code yet or backend-specific result internals.
- The evaluation modules are structured so a future `SkeletonResult` wrapper can reuse the same array-level evaluator rather than reimplementing metrics.
- The original top-level MCP modules remain in place for compatibility and traceability while the framework package becomes the primary path.
- Graph-native backends such as `laplacian` must adapt to `SkeletonResult.skeleton` by rasterizing their internal graph output; optional graph files remain backend extras rather than replacing the common volume contract.

Release tooling:

- `.github/PULL_REQUEST_TEMPLATE.md` captures the change description and version choice.
- `.github/workflows/version-check.yml` validates PR choices using the standard-library helper `scripts/release_version.py`.
- `.github/workflows/release.yml` releases only merged, same-repository `dev → main` PRs. It commits the selected increment to the authoritative `pyproject.toml`, tags that commit, and creates GitHub release notes from the PR.
- Release tooling remains separate from the Python package and its algorithm, evaluation, and visualization layers. See [release setup and recovery](releases.md).
