# Development Log

## 2026-05-19 AEST

### Laplacian output rasterization source

1. Summary of what changed
- Changed the Laplacian backend's standard NIfTI output to rasterize the refined pre-cleaning `graph_original` instead of the cleaned `graph_output` graph.
- Kept `--graph_output`, `--graph_original`, and the framework-level `SkeletonResult.graph` behavior unchanged.
- Added Laplacian metadata recording `rasterized_output_source: graph_original`.
- Updated the Laplacian rasterizer so degree-2 chains use quadratic Bezier interpolation through local graph-node triples, then enforce 26-connected voxel paths between sampled points.

2. Assumptions and constraints
- Graph topology drives output connectivity: graph node degree determines how many graph-connected voxel directions may emerge, but exact occupied 26-neighbor counts are not forced after rounding or clipping.
- Bezier interpolation is limited to degree-2 chains. Branch/end edges and two-node paths continue to use straight 26-connected interpolation.
- The change is localized to the Laplacian backend, rasterizer, focused tests, and documentation.

3. Tests run
- `python -m py_compile skelhub/algorithms/laplacian/*.py`
- `python -m pytest tests/test_laplacian_backend.py -q`

## 2026-05-15 AEST

### Flux backend

1. Summary of what changed
- Added the Python-native flux-driven medial curve backend, registered as `flux`.
- Implemented strict binary-volume validation, signed-distance construction, Gaussian-smoothed gradient/AOF computation, and topology-preserving priority thinning.
- Added CLI flags for flux threshold, sigma, and sigma units.
- Updated README and algorithm documentation with usage, parameters, and provenance notes.

2. Files added, removed, or modified
- Added `skelhub/algorithms/flux/`.
- Added `tests/test_flux_backend.py`.
- Modified `skelhub/algorithms/__init__.py`, `skelhub/cli/main.py`, `README.md`, `docs/algorithms.md`, and `docs/LOG.md`.

3. Architecture decisions made
- Kept all flux-specific distance, AOF, topology, and thinning logic isolated inside `skelhub.algorithms.flux`.
- Preserved SkelHub's standard NIfTI run path and returned only a same-shape binary `uint8` skeleton volume; no graph output is produced by this backend.
- Did not include vessel surface to binary conversion; the backend accepts binary image volumes only.

4. Original source, license, and acknowledgement
- Reference path inspected: `/scratch/user/uqmxu4/Tools/vmtk`.
- VMTK's local `LICENSE` is BSD-style and permits redistribution with copyright/license notice retention.
- The implementation is Python-native from scratch and does not copy VMTK C++ or Python source. Backend metadata and docs acknowledge the VMTK/EvoLib medial-curve behavior and Bouix-Siddiqi-Tannenbaum flux-driven centerline extraction reference.

5. Assumptions
- Backend name is `flux`.
- Valid input values are exactly `{0, 1}`; `{0, 255}` and other non-binary values are rejected.
- Default parameters follow the VMTK public wrapper: threshold `0.0`, sigma `0.5`.
- `--flux-sigma-unit physical` is the default, with `voxels` available for direct voxel-space smoothing.

6. Tests run
- `python -m py_compile skelhub/algorithms/flux/config.py skelhub/algorithms/flux/medial_curve.py skelhub/algorithms/flux/backend.py skelhub/algorithms/flux/__init__.py skelhub/algorithms/__init__.py skelhub/cli/main.py`
- `python -m pytest tests/test_flux_backend.py -q`
- `python -m pytest tests/test_flux_backend.py tests/test_framework_cli.py -q`

7. Remaining risks or recommended next steps
- Compare outputs visually against representative VMTK medial-curve outputs when reference binary-image cases are available.

## 2026-05-13 AEST

### Palagyi-Kuba backend

1. Summary of what changed
- Added the Python-native Palagyi-Kuba 12-subiteration thinning backend, registered as `palagyi_kuba`.
- Added curve and surface modes, PK-specific CLI flags, explicit template inventories, direction scheduling, topology guards, and standard `SkeletonResult` metadata.
- Updated README and algorithm documentation with usage and parameter notes.

2. Files added, removed, or modified
- Added `skelhub/algorithms/palagyi_kuba/`.
- Added `tests/test_palagyi_kuba_backend.py`.
- Modified `skelhub/algorithms/__init__.py`, `skelhub/cli/main.py`, `README.md`, `docs/algorithms.md`, and `docs/LOG.md`.

3. Architecture decisions made
- Kept all PK-specific template, direction, endpoint, and thinning code inside `skelhub.algorithms.palagyi_kuba`.
- Used SkelHub's standard NIfTI run path and returned only a binary same-shape skeleton volume; no graph output is produced by this backend.
- Recorded the implementation's signed axis convention and source template filenames in backend metadata for traceability.

4. Assumptions
- None left open from the implementation plan: curve and surface modes are both exposed; non-binary input is thresholded at `0.5` by default; axis and sign conventions follow the user-approved mapping.

5. Tests run
- `python -m py_compile skelhub/algorithms/palagyi_kuba/config.py skelhub/algorithms/palagyi_kuba/directions.py skelhub/algorithms/palagyi_kuba/templates.py skelhub/algorithms/palagyi_kuba/thinning.py skelhub/algorithms/palagyi_kuba/backend.py skelhub/algorithms/palagyi_kuba/__init__.py skelhub/algorithms/__init__.py skelhub/cli/main.py`
- `python -m pytest tests/test_palagyi_kuba_backend.py -q`
- `python -m pytest tests/test_palagyi_kuba_backend.py tests/test_framework_cli.py -q`

6. Remaining risks or recommended next steps
- Visually compare curve and surface outputs against known Palagyi-Kuba reference outputs when small reference volumes are available.

### L1 v2 refinements

1. Summary of what changed
- Implemented the v2 L1-medial skeleton refinement path inside `skelhub.algorithms.l1_skeleton`.
- Added inverse local-density weighting during attraction, branch-curve extraction from high-confidence contracted samples, endpoint merging, final branch smoothing/segmentation, and branch-local ellipse re-centering based on the `ALGORITHM.md` additional note.
- Added `--l1-output-mode {branches,points}` so the default output rasterizes final branch curves while the earlier contracted-point output remains available for comparison.
- Added CLI/config toggles for density weighting and ellipse re-centering.

2. Files added, removed, or modified
- Modified `skelhub/algorithms/l1_skeleton/config.py`, `skeleton.py`, `rasterize.py`, and `backend.py`.
- Modified `skelhub/cli/main.py`.
- Modified `tests/test_l1_skeleton_backend.py`.
- Modified `README.md`, `docs/algorithms.md`, `docs/architecture.md`, and `docs/LOG.md`.

3. Architecture decisions made
- Kept the implementation Python-native rather than copying C++ source because the local L1-Skeleton reference still has unclear license coverage and UI-heavy C++ dependencies.
- Treated branches as L1-internal data, not framework graphs; the backend still returns a standard binary `SkeletonResult.skeleton` and leaves `SkeletonResult.graph` unset.
- Used `/scratch/user/uqmxu4/Tools/Skel_Refs/L1-Skeleton/ALGORITHM.md` as the authority for ellipse re-centering because the C++ tree exposes only a `Need Recentering` parameter, not a concrete implementation path.

4. Assumptions
- Foreground voxels remain `data > 0`; outputs remain binary `{0, 1}` `uint8`.
- Branch mode is the v2 default. Point mode exists for regression and visual comparison with the earlier contraction-only behavior.
- The ellipse re-centering fit is skipped when a branch node has too few cross-section points, with attempted/applied counts recorded in metadata.

5. Tests run
- `python -m py_compile skelhub/algorithms/l1_skeleton/config.py skelhub/algorithms/l1_skeleton/skeleton.py skelhub/algorithms/l1_skeleton/rasterize.py skelhub/algorithms/l1_skeleton/backend.py skelhub/cli/main.py`
- `python -m pytest tests/test_l1_skeleton_backend.py -q`
- `python -m pytest tests/test_framework_cli.py -q`

6. Remaining risks or recommended next steps
- Compare v2 branch outputs against representative real L1-Skeleton reference cases when a runnable/reference output is available.
- Tune branch-search thresholds for highly anisotropic or sparse foreground volumes if visual inspection shows over-merged or under-segmented branches.

1. Summary of what changed
- Added the Python-native L1-medial skeleton backend, registered as `l1_skeleton`.
- Implemented foreground voxel to point-cloud sampling, KDTree-based L1 attraction and conditional repulsion, PCA directionality scoring, and point rasterization.
- Added CLI flags for L1 sampling, radius scheduling, convergence, repulsion, and deterministic seeding.
- Documented provenance and license status for the local L1-Skeleton C++ reference repository.

2. Files added, removed, or modified
- Added `skelhub/algorithms/l1_skeleton/`.
- Added `tests/test_l1_skeleton_backend.py`.
- Modified `.gitignore`, `skelhub/algorithms/__init__.py`, `skelhub/cli/main.py`, `README.md`, `docs/algorithms.md`, `docs/architecture.md`, and `docs/LOG.md`.

3. Architecture decisions made
- Implemented a Python-native backend instead of binding the C++/Qt reference code because the original repo does not include a clear license file and has heavyweight UI/build dependencies.
- Kept L1-specific point-cloud contraction and rasterization isolated inside `skelhub.algorithms.l1_skeleton`.
- Removed the earlier sparse graph builder and optional GraphML output because that processing path was not part of the original L1-Skeleton codebase.
- Returned a standard binary `SkeletonResult.skeleton`; `SkeletonResult.graph` is left unset for this backend.

4. Assumptions
- Foreground voxels are `data > 0`; outputs are binary `{0, 1}` `uint8`.
- Density weighting, ellipse re-centering, and the original branch-search/final-segmentation machinery are deferred refinements.
- Spacing is used as a simple per-axis scale for point coordinates when available.

## 2026-05-08 AEST

1. Summary of what changed
- Extended `skelhub graphviz` so the PyVista viewer can load both GraphML files and binary NIfTI volumes in the same session.
- Added NIfTI validation that accepts exactly binary `{0, 1}` values, renders foreground voxels as unit blocks, and rejects non-binary volumes with a warning.
- Added mixed-format import/drop handling, type labels in the top-left file list, and slider visibility rules that hide graph appearance sliders for active NIfTI files while keeping command buttons available.
- Updated README and CLI help text for GraphML/NIfTI viewer support.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `skelhub/visualization/__init__.py`.
- Modified `skelhub/cli/main.py`.
- Modified `skelhub/api.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `README.md` and `docs/LOG.md`.

3. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py tests/test_graph_visualization.py`
- `python -m pytest tests/test_graph_visualization.py -q`
- `python -m pytest tests/test_framework_cli.py::test_framework_graphviz_cli_reports_missing_coordinates -q`
- `python -m skelhub graphviz --help`

## 2026-05-07 18:34:15 AEST

1. Summary of what changed
- Added the VascGraph Laplacian graph-contraction skeletonization path as SkelHub's third backend, registered as `laplacian`.
- Ported the required graph generation, contraction, refinement, node cleaning, 26-connected rasterization, and cleaned GraphML export into `skelhub.algorithms.laplacian`.
- Added CLI support for `--graph_output`, `--graph_original`, and the Laplacian parameters from `VascularGraph/demo_skeleton.py`.
- Updated README and algorithm/architecture docs for the new backend.

2. Files added, removed, or modified
- Added `skelhub/algorithms/laplacian/`.
- Added `tests/test_laplacian_backend.py`.
- Modified `.gitignore` to allow the new Laplacian test file to be tracked.
- Modified `skelhub/algorithms/__init__.py`.
- Modified `skelhub/cli/main.py`.
- Modified `pyproject.toml` and `requirements.txt` to declare NetworkX as a direct dependency.
- Modified `README.md`, `docs/algorithms.md`, `docs/architecture.md`, and `docs/LOG.md`.

3. Architecture decisions made
- Kept the backend self-contained instead of importing VascularGraph at runtime, because the original code relies on old NetworkX APIs.
- Preserved the graph-native algorithm internally while returning SkelHub's standard rasterized skeleton NIfTI output.
- Wrote optional GraphML from the cleaned graph with world-coordinate `X`, `Y`, `Z` fields and explicit voxel-position metadata.
- Added optional GraphML export for the refined graph before `post_node_cleaning()`.

4. Assumptions
- The backend name is `laplacian`.
- Demo defaults from `VascularGraph/demo_skeleton.py` are the public SkelHub defaults.
- Rasterized graph edges should be binary and 26-connected within the source volume shape.

5. Tests run
- `python -m py_compile skelhub/algorithms/laplacian/*.py skelhub/algorithms/__init__.py skelhub/cli/main.py`
- `python -m pytest tests/test_laplacian_backend.py -q`
- `python -m pytest tests/test_laplacian_backend.py tests/test_framework_cli.py tests/test_lee94_backend.py tests/test_graphgen.py -q`
- `python -m pytest tests/test_laplacian_backend.py tests/test_framework_cli.py -q`
- `python -m pytest -q` completed with 92 passed and 2 unrelated failures: `tests/test_evaluation_metrics.py::test_endpoint_count_uses_6_connectivity_for_diagonal_tip_cases` and `tests/test_graph_visualization.py::test_slider_setup_uses_separated_right_aligned_compact_positions`.
- `python -m py_compile skelhub/algorithms/laplacian/config.py skelhub/algorithms/laplacian/skeleton.py skelhub/algorithms/laplacian/backend.py skelhub/cli/main.py`
- `python -m skelhub run --algorithm laplacian --input /tmp/skelhub_laplacian_graph_original/input.nii.gz --output /tmp/skelhub_laplacian_graph_original/output.nii.gz --graph_output /tmp/skelhub_laplacian_graph_original/clean.graphml --graph_original /tmp/skelhub_laplacian_graph_original/original.graphml --verbose`
- `python -m skelhub run --algorithm laplacian --input /tmp/skelhub_laplacian_graph_original/input.nii.gz --output /tmp/skelhub_laplacian_graph_original/output_no_graph_original.nii.gz --verbose`

## 2026-05-05 18:10:21 AEST

1. Summary of what changed
- Moved the graph viewer's node-size and edge-thickness sliders farther left while keeping them compact and away from the window boundary.
- Replaced text-background-only command buttons with fixed-size rectangle-backed overlay buttons so the button backgrounds cover their glyphs.
- Replaced the previous `Reset View` behavior with saved initial-camera-state restoration for the active loaded graph.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `README.md`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Added a small `CameraState` model and store the initial camera state on each loaded GraphML entry after its first default render.
- Kept `Reset View` separate from `Refresh`; it restores camera state only and does not rebuild meshes or apply preview slider values.
- Used VTK 2D rectangle actors behind command labels, with a fallback text-background path if the rectangle actor imports are unavailable.

4. Assumptions
- `Reset View` should restore the graph's initial default orientation/framing, not just call `plotter.reset_camera()` from the current orientation.
- Slider span `0.66` to `0.86` provides a clearer left shift while keeping a visible right-side margin.
- Fixed button backgrounds should cover text and icon glyphs with padding.

5. Limitations
- Button rectangles are custom VTK/PyVista overlay actors rather than native GUI controls.
- Camera-state capture depends on the PyVista/VTK camera exposing standard position, focal point, view-up, clipping range, and parallel-scale accessors.
- Live desktop review is still needed to confirm exact glyph centering and rectangle layering across display scaling settings.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py tests/test_graph_visualization.py`
- `python -m pytest tests/test_graph_visualization.py -q`

7. Remaining risks or recommended next steps
- Manually run `python -m skelhub graphviz` and verify the slider position, button background coverage, and Reset View after rotating/zooming the camera.

## 2026-05-05 17:52:46 AEST

1. Summary of what changed
- Adjusted the pure-PyVista `skelhub graphviz` overlay layout based on the latest screenshot review.
- Increased vertical separation between the node-size and edge-thickness sliders and kept the compact slider cluster right-aligned with a visible window margin.
- Moved the command controls into an evenly spaced, same-height, bottom-right aligned row.
- Added a blue `Reset View` button next to the red `Refresh` button; it resets camera framing without changing loaded files, meshes, or slider values.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `README.md`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Kept the controls as pure PyVista/VTK overlay text actors with explicit hitboxes and did not add a native GUI layer.
- Added a small `reset_active_view(...)` helper so camera reset is separate from graph rebuilding and refresh-driven appearance changes.
- Computed command button positions from the current plotter window width so the row stays right-aligned with a fixed margin.

4. Assumptions
- `Reset View` means `plotter.reset_camera()` plus render, not resetting files, style values, or graph contents.
- The command row should sit near the bottom-right with a fixed margin from the window edges.
- Wider slider vertical spacing is preferred over keeping the two sliders tightly grouped.

5. Limitations
- The command buttons are still text-actor overlays rather than native widgets, so exact visual dimensions need desktop review.
- Slider placement uses normalized PyVista viewport coordinates; the layout should be checked on both normal and maximized window sizes.
- The local automated checks do not manually exercise the live desktop window.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py tests/test_graph_visualization.py`
- `python -m pytest tests/test_graph_visualization.py -q`

7. Remaining risks or recommended next steps
- Manually run `python -m skelhub graphviz` in a desktop-capable environment and review slider overlap, bottom-right row spacing, and Reset View behavior after rotating/zooming the camera.

## 2026-05-05 17:29:31 AEST

1. Summary of what changed
- Polished the pure-PyVista `skelhub graphviz` overlay based on the desktop screenshot review.
- Replaced the large top-left status text with a compact opaque file label that unfolds into a loaded-file list on hover.
- Replaced checkbox-style command controls with custom opaque hitbox buttons for `Import`, `Close`, `<`, `>`, and a red `Refresh`.
- Restyled the node-size and edge-thickness sliders into a smaller upper-right cluster using silver/steel PyVista slider styling.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `README.md`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Kept the viewer pure PyVista and implemented the file list and buttons as overlay text actors with explicit hitboxes and VTK mouse observers.
- Retained the existing session model and graph rendering behavior; the change is limited to overlay controls and event dispatch.
- Kept refresh-based slider application so large graphs are not rebuilt on every slider drag event.

4. Assumptions
- Hovering the top-left file label is the intended trigger for showing the loaded-file list.
- Clicking a filename in the unfolded list should switch the active graph immediately.
- Silver/steel compact 2D sliders are an acceptable approximation of the requested metallic style in pure PyVista.

5. Limitations
- The file list and buttons are custom PyVista/VTK overlays, not native GUI widgets.
- PyVista's 2D slider widget does not support true metallic sphere materials, so the implementation uses metallic-looking colors and compact styling.
- The local automated checks do not manually exercise live hover/click behavior in a desktop window.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py tests/test_graph_visualization.py`
- `python -m pytest tests/test_graph_visualization.py -q`
- `python -m pytest tests/test_graph_visualization.py tests/test_framework_cli.py::test_framework_graphviz_cli_reports_missing_coordinates -q`
- `python -m skelhub graphviz --help`

7. Remaining risks or recommended next steps
- Manually run `python -m skelhub graphviz` in a desktop-capable environment and review top-left hover behavior, filename click accuracy, command-button sizing, and slider readability.
- If text-actor button backgrounds still feel too text-shaped on the target desktop, consider adding thin rectangle actors behind the text while keeping the same hitbox dispatch.

## 2026-05-05 15:23:26 AEST

1. Summary of what changed
- Added pure-PyVista session controls to `skelhub graphviz` so one viewer can load multiple GraphML files while displaying one active graph at a time.
- Added in-canvas `Import`, `Close`, `Prev`, `Next`, and `Refresh` controls, plus node-size and edge-thickness sliders whose preview values apply on refresh.
- Added best-effort `.graphml` drag-and-drop handling through VTK drop-file events when the active render-window backend supports them.
- Kept the existing CLI/API contract for empty launches, initial `--input`, `--node_size`, and `--edge_thickness`.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `skelhub/visualization/__init__.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `README.md`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Kept the viewer on pure PyVista instead of adding a Qt application shell, so controls are VTK/PyVista overlays rather than native menus or dock widgets.
- Added a local `GraphViewerSession` state model for loaded files, active file selection, preview slider values, committed appearance options, and current graph actors.
- Rebuilds active graph actors only when switching files, closing files, importing files, dropping files, or pressing `Refresh`; slider movement alone updates preview state.
- Used a small Tk file dialog for local import because pure PyVista does not provide a native file picker.

4. Assumptions
- Re-loading the same GraphML path should reactivate the existing session entry instead of adding a duplicate.
- Dropping several valid GraphML files should load them all and activate the first valid file in the dropped batch.
- Slider ranges of `0.5` to `40.0` for node size and `0.1` to `10.0` for edge thickness are practical defaults for this pure-PyVista viewer.

5. Limitations
- There is no native `File` dropdown, native `Tool` tab, docked sidebar, or separate adjacent tool window in this implementation.
- The in-canvas controls are simple PyVista/VTK widgets, so their final look and placement must be reviewed in a desktop session.
- Drag-and-drop depends on whether the active VTK/PyVista desktop backend emits `DropFilesEvent` with file paths.
- The local automated checks do not manually exercise the interactive desktop window.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py tests/test_graph_visualization.py`
- `python -m pytest tests/test_graph_visualization.py -q`
- `python -m pytest tests/test_graph_visualization.py tests/test_framework_cli.py::test_framework_graphviz_cli_reports_missing_coordinates -q`
- `python -m skelhub graphviz --help`

7. Remaining risks or recommended next steps
- Manually run `python -m skelhub graphviz` in a desktop-capable environment and review the in-canvas controls, file dialog, drag-and-drop behavior, and refresh-time performance on representative GraphML files.
- If drag-and-drop does not fire on the target desktop backend, keep `Import` as the supported local-file path and revisit a Qt shell only if native drop behavior becomes essential.

## 2026-04-29 15:51:59 AEST

1. Summary of what changed
- Rewrote `skelhub graphviz` from the old PySide6/Qt3D implementation to a lightweight PyVista-based GraphML viewer.
- Kept the public `skelhub graphviz` command and `launch_graph_viewer(...)` API, including the optional empty-viewer launch when `--input` is omitted.
- Reduced the viewer scope to loading GraphML node coordinates and rendering constant-size nodes and edges; removed the old multi-file session, toolbar, rebuild, diagnostics, and appearance-panel behavior.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `skelhub/visualization/__init__.py`.
- Modified `skelhub/cli/main.py`.
- Modified `pyproject.toml`.
- Modified `requirements.txt`.
- Modified `README.md`.
- Modified `docs/architecture.md`.
- Modified `.gitignore` to keep most test artifacts ignored while allowing `tests/test_graph_visualization.py` to be tracked.
- Added `tests/test_graph_visualization.py`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Split visualization responsibilities into GraphML I/O/validation and PyVista scene construction within the visualization module.
- Used `igraph` for GraphML loading and PyVista for rendering, with `pyvista>=0.47,<0.48` as the only new direct visualization dependency.
- Removed direct `PySide6` and `matplotlib` dependencies from SkelHub config; PyVista brings its own render stack transitively.
- Implemented the viewer independently from VesselVio code so the change uses only the general idea of PyVista graph rendering and does not copy GPL-covered implementation details.

4. Assumptions
- SkelHub GraphML node coordinates are supplied as `X`, `Y`, `Z`, with lowercase `x`, `y`, `z` accepted as a small compatibility convenience.
- Radius, length, tortuosity, annotations, movies, file menus, multi-file sessions, and live appearance controls remain out of scope for this first PyVista rewrite.
- `docs/LOG.md` is the project log to update; no root `LOG.md` was created.

5. Limitations
- The local session is headless, so the interactive desktop window was not manually exercised.
- The PyVista offscreen smoke test emits a VTK warning about the missing `DISPLAY`, but still builds and closes the plotter successfully.
- `python -m pytest -q` still has one unrelated evaluation failure in `tests/test_evaluation_metrics.py::test_endpoint_count_uses_6_connectivity_for_diagonal_tip_cases`.

6. Tests run
- `python -m pip install --dry-run 'pyvista>=0.47,<0.48'`
- `python -m pip install 'pyvista>=0.47,<0.48'`
- `python -c "import pyvista, vtk, igraph, numpy; print('imports ok', pyvista.__version__, vtk.vtkVersion.GetVTKVersion())"`
- Direct PyVista offscreen smoke script creating a tiny graph plotter with `build_graph_plotter(..., off_screen=True)`.
- `python -m skelhub graphviz --help`
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py tests/test_graph_visualization.py`
- `python -m pytest tests/test_graph_visualization.py tests/test_framework_cli.py::test_framework_graphviz_cli_reports_missing_coordinates -q` passed with 14 tests.
- `python -m pytest -q` completed with 67 passed and 1 unrelated evaluation failure.

7. Remaining risks or recommended next steps
- Run `python -m skelhub graphviz --input ./test_data/simple_graph/sample.graphml` in a desktop-capable environment to confirm the interactive PyVista window behavior.
- Decide separately whether more of `/tests/` should be tracked; this change only unignores the visualization test file needed for the PyVista rewrite.

## 2026-04-29 12:47:02 AEST

1. Summary of what changed
- Added a Voreen-faithful skeleton-to-protograph GraphML generation path under `skelhub/postprocessing/graphgen/`.
- Implemented the `NeighborCountVoxelClassifier -> connected components -> ProtoGraph` path for 3D skeleton volumes, including 26-neighborhood classification, end/regular/branch grouping, synthetic support nodes for freestanding regular loops, direct node-to-node empty edges, and GraphML export.
- Added the unified CLI command `skelhub graphgen -i INPUT -o OUTPUT` and a public API wrapper for generating GraphML from a skeleton NIfTI.

2. Files added, removed, or modified
- Added `skelhub/postprocessing/graphgen/classification.py`.
- Added `skelhub/postprocessing/graphgen/components.py`.
- Added `skelhub/postprocessing/graphgen/protograph.py`.
- Added `skelhub/postprocessing/graphgen/graphml.py`.
- Added `skelhub/postprocessing/graphgen/api.py`.
- Added `skelhub/postprocessing/graphgen/__init__.py`.
- Added `tests/test_graphgen.py`.
- Modified `skelhub/postprocessing/__init__.py`.
- Modified `skelhub/api.py`.
- Modified `skelhub/__init__.py`.
- Modified `skelhub/cli/main.py`.
- Modified `LOG.md`.

3. Architecture decisions made
- Placed graph generation in `skelhub/postprocessing/graphgen/` because graphification is a postprocessing stage and should stay separate from algorithm backends and evaluation.
- Left `skelhub/evaluation/graph_generation.py` and `skelhub/evaluation/skel_to_graph.py` untouched because they are legacy/test scripts and are not wired into the new CLI/API path.
- Used a modular Python implementation so classification, component extraction, proto-graph construction, GraphML export, and orchestration can be maintained independently.
- Exported viewer-compatible GraphML node coordinates as `X`, `Y`, and `Z`, with JSON-encoded voxel support and centerline attributes for traceability.

4. Assumptions
- "100% preserved original functionality" means preserving Voreen's skeleton-to-protograph behavior, not the later segmentation-supported `VesselGraph` feature extraction.
- NIfTI nonzero voxels are treated as skeleton foreground.
- The new graphgen path is a postprocessing API/CLI only; evaluation will not call it yet.
- The GraphML output represents proto-graph topology and geometry, not radius, volume, roundness, or other segmentation-derived vessel features.

5. Limitations
- The Python component extraction preserves Voreen's class semantics and proto-graph topology behavior, but it reconstructs connected components with Python/scipy arrays rather than copying Voreen's row-run storage implementation byte-for-byte.
- Edge centerlines are ordered from 26-neighbor adjacency; equivalent topology is the goal, not matching Voreen's temporary run-tree storage order in every tie case.
- The local user-level `pytest` installation still fails during import with `AttributeError: __spec__`, and the repository `.venv` still does not have `pytest` installed.

6. Tests run
- `python -m py_compile skelhub/postprocessing/graphgen/classification.py skelhub/postprocessing/graphgen/components.py skelhub/postprocessing/graphgen/protograph.py skelhub/postprocessing/graphgen/graphml.py skelhub/postprocessing/graphgen/api.py skelhub/postprocessing/__init__.py skelhub/cli/main.py skelhub/api.py skelhub/__init__.py tests/test_graphgen.py`
- Direct Python smoke assertions covering classification, straight-chain graph generation, branch graph generation, synthetic-loop support, and GraphML export/loading.
- `python -m skelhub graphgen -i test_data/lsys_gt/iter_4_8_step_1/Lnet_i4_0_tort_centreline_26conn.nii.gz -o /tmp/skelhub_graphgen_*/lsys.graphml --verbose`, followed by `igraph` loading and non-empty node/edge assertions. The generated graph loaded with 4 nodes and 3 edges.
- `python -m skelhub graphgen --help`
- `python -m skelhub graphviz --help`
- Attempted `python -m pytest tests/test_graphgen.py -q`; blocked by the user-level pytest import error.
- Attempted `.venv/bin/python -m pytest tests/test_graphgen.py -q`; blocked because pytest is not installed in `.venv`.
- Attempted `python -m pytest tests/test_framework_cli.py tests/test_graph_visualization.py -q`; blocked by the same user-level pytest import error.

7. Remaining risks or recommended next steps
- Run `python -m pytest tests/test_graphgen.py tests/test_framework_cli.py tests/test_graph_visualization.py -q` in an environment with a working pytest installation.
- Compare a few small synthetic skeletons against Voreen output directly if exact edge ordering, not just equivalent topology, becomes important.

## 2026-04-29 00:33:15 AEST

1. Summary of what changed
- Fixed the graph viewer appearance panel not showing when the `Appearance` toolbar button was toggled.
- Moved the controls from a QWidget overlay on top of the Qt3D window container into a right-side `QDockWidget`, which avoids native-window stacking issues from `QWidget.createWindowContainer`.
- Kept the existing node size, edge thickness, and panel opacity slider behavior unchanged.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `README.md`.
- Modified `LOG.md`.

3. Architecture decisions made
- Kept the fix local to the visualization window layout and did not change graph loading, scene construction, CLI/API behavior, or algorithm/evaluation code.
- Used Qt's main-window dock system instead of sibling-widget overlay stacking because the Qt3D canvas is hosted as a native child window.
- Kept the right-side toolbar toggle as the single control for showing and hiding the panel.

4. Assumptions
- A right-side dock panel is acceptable for the same tool-panel workflow because it is visible and stable across Qt platforms.
- The current default panel opacity is `0.5`, and the opacity slider now starts at that same value.

5. Limitations
- The panel is beside the canvas rather than painted over the canvas, avoiding the bug but slightly changing the visual placement from the original sketch.
- This environment still cannot manually exercise the live PySide6 desktop window.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/cli/main.py skelhub/api.py`
- `python -m skelhub graphviz --help`

7. Remaining risks or recommended next steps
- Manually launch `python -m skelhub graphviz --input <graph.graphml>` in the target desktop session to confirm the dock appears immediately and toggles correctly.

## 2026-04-29 00:20:23 AEST

1. Summary of what changed
- Added a toolbar-toggled appearance panel to the `skelhub graphviz` viewer, matching the requested upper-right canvas control layout.
- Added real-time sliders for node size, edge thickness, and panel opacity.
- Mapped the edge thickness slider to the effective rendered Qt line-width range, now `2.0` to `10.0`, and kept slider values bounded to the supported intervals.
- Removed the unused `_edge_radius` scene metric path so edge sizing has one active implementation path.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `README.md`.
- Modified `LOG.md`.

3. Architecture decisions made
- Kept the change isolated to the visualization layer; CLI parsing, graph loading, algorithms, evaluation, and framework API behavior are unchanged.
- Reused the existing scene rebuild path for live appearance updates instead of adding a separate renderer mutation path.
- Suppressed repeated diagnostic prints during slider-driven rebuilds so interactive updates do not flood the terminal.

4. Assumptions
- The node size slider uses a practical viewer-control interval of `0.5` to `40.0` because node size previously had only a positive-value validation and no renderer upper bound.
- The edge thickness slider uses the backend's effective rendered line-width interval, mapping `edge_thickness * 1.6` onto `2.0` to `10.0`.
- The appearance panel starts visible and can be hidden from the right side of the toolbar with the `Appearance` toggle.

5. Limitations
- The panel rebuilds the active graph scene while sliders move; very large graphs may feel less smooth than a renderer with mutable per-entity style state.
- The local environment could compile and smoke-check the viewer logic, but it was not possible to manually exercise the live PySide6 window in this session.
- The user-level `pytest` installation fails during import with `AttributeError: __spec__`, and the repository `.venv` does not have `pytest` installed.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py tests/test_graph_visualization.py skelhub/cli/main.py skelhub/api.py`
- `.venv/bin/python -m py_compile skelhub/visualization/graph_viewer.py tests/test_graph_visualization.py skelhub/cli/main.py skelhub/api.py`
- Direct Python smoke script checking edge thickness range mapping and scene metric construction.
- Attempted `python -m pytest tests/test_graph_visualization.py -q`; blocked by the user-level pytest import error.
- Attempted `.venv/bin/python -m pytest tests/test_graph_visualization.py -q`; blocked because pytest is not installed in `.venv`.

7. Remaining risks or recommended next steps
- Manually launch `python -m skelhub graphviz --input <graph.graphml>` in a desktop PySide6 environment to confirm the overlay stacking works above `QWidget.createWindowContainer` on the target platform.
- If the live rebuild path is too slow on large vessel graphs, add a short Qt debounce timer or migrate edge/node styling to mutable render-state objects.

## 2026-04-20 22:00:36 AEST

1. Summary of what changed
- Replaced the evaluation placeholder with the first working voxel-based evaluation subsystem under `skelhub/evaluation/` for paired binary 3D predicted/reference skeleton volumes.
- Implemented geometry preservation with the buffer method, 3D morphology quality metrics, normalized quality variants, and the global performance score `P`.
- Extended the unified CLI and framework API so `skelhub evaluate` now requires prediction, reference, and buffer-radius inputs, always prints a report, and can optionally emit structured JSON output.

2. Files added, removed, or modified
- Added `skelhub/evaluation/evaluator.py`.
- Added `skelhub/evaluation/geometry.py`.
- Added `skelhub/evaluation/morphology.py`.
- Added `skelhub/evaluation/reporting.py`.
- Added `skelhub/evaluation/validation.py`.
- Modified `skelhub/core/models.py`.
- Modified `skelhub/evaluation/__init__.py`.
- Removed `skelhub/evaluation/placeholder.py`.
- Modified `skelhub/api.py`.
- Modified `skelhub/cli/main.py`.
- Added `tests/test_evaluation_metrics.py`.
- Removed `tests/test_evaluation_placeholder.py`.
- Modified `tests/__init__.py`.
- Modified `README.md`.
- Modified `docs/evaluation.md`.
- Modified `docs/architecture.md`.
- Modified `LOG.md`.

3. Architecture decisions made
- Kept the v1 evaluator purely voxel-based and algorithm-agnostic, with no dependency on MCP internals and no coupling to `graph_generation.py` or `skel_to_graph.py`.
- Split evaluation responsibilities into validation, geometry, morphology, reporting, and orchestration modules so future extensions can add metrics or `SkeletonResult` wrappers without rewriting the core array-level evaluator.
- Extended the shared framework-level `EvaluationResult` instead of inventing a separate result container, while keeping the new fields explicit enough for terminal and JSON reporting.

4. Assumptions
- The v1 morphology metrics should use signed differences relative to reference counts when those counts are non-zero, with explicit fallback behavior and warnings when a reference count is zero.
- Zero-denominator geometry cases should resolve to `1.0` only when both skeletons are empty; otherwise they should resolve to `0.0` with a warning so the behavior stays explicit and stable.
- Physical buffer radii in micrometers should only be accepted when the underlying image spacing units are convertible from the NIfTI header.

5. Limitations
- The evaluator is 3D only and expects raw binary skeleton inputs; it does not resample, threshold, or repair invalid data automatically.
- The implementation is voxel-based only and does not yet compute graph-based metrics or consume `SkeletonResult` objects as the main public input path.
- Physical micrometer radii depend on usable NIfTI spatial units; files with unknown spatial units will fail clearly for `--buffer-radius-unit um`.

6. Tests run
- `python -m pytest /scratch/user/uqmxu4/Tools/SkelHub/tests/test_evaluation_metrics.py -q`
- `python -m pytest /scratch/user/uqmxu4/Tools/SkelHub/tests/test_framework_core.py /scratch/user/uqmxu4/Tools/SkelHub/tests/test_framework_cli.py -q`

7. Remaining risks or recommended next steps
- Add a thin `SkeletonResult`-aware wrapper so framework-produced skeleton outputs can flow into the same evaluator without going back to disk first.
- Consider whether future revisions should expose more formal metric sub-objects inside `EvaluationResult` once the metric set grows beyond the current v1 surface.
- Manually exercise `skelhub evaluate` on representative real NIfTI skeleton pairs, especially anisotropic datasets and micrometer-radius runs, to confirm the warning and reporting ergonomics feel right.

## 2026-04-15 00:00:02 AEST

1. Summary of what changed
- Updated `skelhub graphviz` so `--input` is now optional: the viewer can start either with an initial GraphML file loaded or in an empty state.
- Kept the existing toolbar-based file-management workflow and connected the empty-start path to the same session model used for later interactive loads.
- Added focused non-GUI tests covering both empty viewer launch and CLI help output for the optional input form.

2. Files added, removed, or modified
- Modified `skelhub/cli/main.py`.
- Modified `skelhub/api.py`.
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `tests/test_framework_cli.py`.
- Modified `README.md`.
- Modified `LOG.md`.

3. Architecture decisions made
- Kept the behavior change limited to the graph viewer CLI path and visualization launch flow; algorithm execution and other CLI commands are unchanged.
- Preserved the separation between CLI argument handling, framework API dispatch, viewer session state, and graph loading/rendering logic.
- Reused the existing empty-scene handling already present in the viewer instead of introducing a new parallel launch path.

4. Assumptions
- Opening an empty viewer window is a valid and useful default when users want to browse for GraphML files interactively after launch.
- Strict validation should remain unchanged once a GraphML path is actually provided, whether through the CLI or the toolbar.

5. Limitations
- This workspace still does not have `PySide6` installed, so the empty-start and initial-file-start flows could only be verified with stubbed non-GUI tests here.
- The CLI now permits `skelhub graphviz` without `--input`, but launching still requires the optional viewer dependencies and a desktop-capable environment.

6. Tests run
- `python -m py_compile /scratch/user/uqmxu4/Tools/SkelHub/skelhub/visualization/graph_viewer.py /scratch/user/uqmxu4/Tools/SkelHub/skelhub/cli/main.py /scratch/user/uqmxu4/Tools/SkelHub/skelhub/api.py /scratch/user/uqmxu4/Tools/SkelHub/tests/test_graph_visualization.py /scratch/user/uqmxu4/Tools/SkelHub/tests/test_framework_cli.py`
- `python -m skelhub graphviz --help`
- Direct Python smoke script stubbing the Qt window layer to confirm `launch_graph_viewer(None)` starts with an empty session and `launch_graph_viewer(path)` starts with one active loaded file.

7. Remaining risks or recommended next steps
- In a desktop-capable environment with `PySide6` installed, manually verify both `python -m skelhub graphviz` and `python -m skelhub graphviz --input ./test_data/simple_graph/sample.graphml` to confirm the empty-state and preloaded-state window behavior feels correct.

## 2026-04-15 00:00:01 AEST

1. Summary of what changed
- Extended the Qt3D graph viewer window into a toolbar-based file-management UI with a `File` menu for loading, unloading, and switching between GraphML files during one viewer session.
- Added explicit viewer-session state tracking for loaded files and the active file while keeping GraphML loading and scene rendering concerns separated.
- Preserved the existing `skelhub graphviz --input ...` flow so the CLI-provided file becomes the initially active entry in the new menu.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `README.md`.
- Modified `LOG.md`.

3. Architecture decisions made
- Kept the change localized to `skelhub.visualization` instead of spreading viewer state into CLI or framework orchestration code.
- Separated responsibilities inside the viewer module into session state, scene switching, and window/menu actions so future viewer actions can extend the same seam without redesigning the subsystem.
- Reused the existing GraphML loading path and scene builder so rendering behavior and graph parsing rules stay unchanged.

4. Assumptions
- Re-loading the same GraphML file in one session should not create duplicate session entries; it should simply reactivate the already loaded file.
- When unloading the current file while others remain loaded, switching to the next remaining entry in load order is a clear default behavior.

5. Limitations
- This workspace still does not have `PySide6` installed, so the new toolbar could not be exercised in a live desktop session here.
- The loaded-file list currently uses menu entries with a checkmark indicator and path-based labels; richer recent-file or rename behavior is intentionally out of scope.

6. Tests run
- `python -m py_compile /scratch/user/uqmxu4/Tools/SkelHub/skelhub/visualization/graph_viewer.py /scratch/user/uqmxu4/Tools/SkelHub/tests/test_graph_visualization.py /scratch/user/uqmxu4/Tools/SkelHub/skelhub/cli/main.py /scratch/user/uqmxu4/Tools/SkelHub/skelhub/api.py`
- Direct Python smoke script importing `skelhub.visualization.graph_viewer`, loading sample GraphML files through `GraphViewerSession`, and verifying duplicate-load, switch, and unload-to-empty-state behavior.
- `python -m skelhub graphviz --help`

7. Remaining risks or recommended next steps
- Run `python -m skelhub graphviz --input ./test_data/simple_graph/sample.graphml` in a desktop-capable environment with `PySide6` available to confirm the toolbar/menu interaction and scene swapping feel right in practice.

## 2026-04-15 00:00:00 AEST

1. Summary of what changed
- Fixed the blank `skelhub graphviz` window regression by reworking the PySide6 Qt3D viewer's scene sizing, camera framing, and material setup.
- Replaced fragile nested Qt binding access with canonical PySide6 Qt3D classes so scene construction is less likely to fail silently.
- Added focused non-GUI tests for scene metrics and sample-graph entity counts to guard against future “window opens but nothing is visible” regressions.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `tests/test_graph_visualization.py`.

3. Architecture decisions made
- Kept the fix localized to the visualization backend without changing CLI or framework API behavior.
- Preserved the current Qt3D rendering model using sphere nodes and cylinder edges instead of broadening scope into a custom renderer rewrite.
- Moved first-launch visibility decisions into explicit scene-metric helpers so the behavior is testable without a live GUI runtime.

4. Assumptions
- The blank viewer was caused by render-scale and camera-framing issues rather than GraphML parsing, because the command already fails clearly when coordinates are missing.
- Ensuring visibility on initial launch is more important than matching the previous `pyqtgraph` viewer's exact apparent sizing.

5. Limitations
- This workspace still does not have `PySide6` installed, so the final interactive desktop launch could not be verified locally here.
- The new tests validate scene math and renderable counts, but they do not provide a pixel-level image assertion of the final Qt3D frame.

6. Tests run
- `python -m py_compile /scratch/user/uqmxu4/Tools/SkelHub/skelhub/visualization/graph_viewer.py /scratch/user/uqmxu4/Tools/SkelHub/tests/test_graph_visualization.py /scratch/user/uqmxu4/Tools/SkelHub/skelhub/cli/main.py /scratch/user/uqmxu4/Tools/SkelHub/skelhub/api.py`
- Direct smoke script confirming `load_graph_visualization_data()` loads `test_data/simple_graph/sample.graphml`, `_scene_entity_counts()` returns `(3, 3)`, and `_compute_scene_metrics()` now yields visibly sized radii and a bounded camera distance.
- `python -m skelhub graphviz --help`

7. Remaining risks or recommended next steps
- Install `PySide6` in a desktop-capable environment and manually run `python -m skelhub graphviz --input ./test_data/simple_graph/sample.graphml` to confirm the graph is visible immediately and the orbit controls feel right.

## 2026-04-14 00:00:04 AEST

1. Summary of what changed
- Migrated `skelhub graphviz` from the previous `pyqtgraph`/`PyQt6`/`PyOpenGL` dependency path to a localized `PySide6` Qt3D implementation.
- Kept the existing GraphML loading path, CLI contract, and appearance flags while replacing the viewer window and scene construction backend.
- Updated packaging, tests, and documentation so the optional graph-visualization extra now installs `PySide6` instead of the previous stack.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `skelhub/cli/main.py`.
- Modified `pyproject.toml`.
- Modified `README.md`.
- Modified `docs/architecture.md`.
- Modified `tests/test_graph_visualization.py`.

3. Architecture decisions made
- Kept CLI and framework orchestration thin: `skelhub.cli` and `skelhub.api` still dispatch into `skelhub.visualization` without introducing a new cross-cutting abstraction.
- Preserved lazy optional GUI imports so base package installs and non-graph CLI paths remain unaffected.
- Used a minimal Qt3D scene graph with shared sphere and cylinder meshes to keep the migration focused on backend replacement rather than a broader visualization redesign.

4. Assumptions
- A `PySide6`-only optional dependency is acceptable for the graph viewer feature and is preferred over retaining mixed Qt bindings or `pyqtgraph`.
- The intended GraphML inputs continue to provide explicit 3D node coordinates through `X`, `Y`, `Z` or existing compatibility fallbacks.

5. Limitations
- The new viewer renders node and edge thickness in scene-space Qt3D geometry rather than the old pixel-space `pyqtgraph` primitives, so apparent sizing can vary somewhat with graph scale and camera distance.
- Large graphs may render more slowly than the previous OpenGL line/scatter path because the minimal migration uses Qt3D entities for spheres and cylinders instead of a custom batched renderer.
- This workspace does not currently have `PySide6` installed, so the successful optional-dependency import path could only be covered by a skipped test rather than an executed local runtime check.

6. Tests run
- `python -m py_compile /scratch/user/uqmxu4/Tools/SkelHub/skelhub/visualization/graph_viewer.py /scratch/user/uqmxu4/Tools/SkelHub/skelhub/cli/main.py /scratch/user/uqmxu4/Tools/SkelHub/skelhub/api.py /scratch/user/uqmxu4/Tools/SkelHub/tests/test_graph_visualization.py /scratch/user/uqmxu4/Tools/SkelHub/tests/test_framework_cli.py`
- `python -m skelhub graphviz --help`
- Direct smoke script confirming `load_graph_visualization_data()` still loads a minimal GraphML file with `X/Y/Z` coordinates and returns the expected node and edge arrays.
- Direct smoke script confirming `python -m skelhub graphviz --input <missing-coordinates.graphml>` exits with code `2` and emits the expected missing-coordinate error.
- Direct smoke script confirming the missing-optional-dependency error now points to `PySide6` and the `.[graphviz]` install extra.
- Attempted `python -m pytest tests/test_graph_visualization.py tests/test_framework_cli.py`, but the environment still fails before collection with the pre-existing `AttributeError: __spec__` issue in the installed `py`/`pytest` stack.

7. Remaining risks or recommended next steps
- Install the optional extra with `python -m pip install -e .[graphviz]` in a desktop-capable environment and manually open a representative GraphML file to validate the interaction feel and default camera framing.
- If very large vessel graphs become a performance bottleneck, consider a future batched Qt3D geometry path, but that was intentionally out of scope for this migration.

## 2026-04-14 00:00:03 AEST

1. Summary of what changed
- Refined the `skelhub graphviz` Qt import diagnostics to distinguish between genuinely missing optional packages and Qt runtime ABI/library conflicts.
- Added environment-aware error details including the active interpreter, detected `skelhub` launch path, and a targeted note for `Qt_6_PRIVATE_API` / `libQt6` shared-library mismatch cases.
- Expanded graph viewer troubleshooting guidance in the README to cover same-interpreter installs and conflicting Qt libraries from `LD_LIBRARY_PATH` or environment modules.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `README.md`.

3. Architecture decisions made
- Kept Qt imports lazy and optional, preserving the current packaging model and CLI behavior outside the graph viewer launch path.
- Limited the fix to dependency-loading diagnostics and documentation rather than changing extras, import topology, or mandatory dependencies.

4. Assumptions
- The reported `Qt_6_PRIVATE_API` failure is caused by incompatible Qt shared libraries being loaded at runtime, not by malformed GraphML input.
- The existing optional dependency declaration remains correct and does not need renaming or restructuring.

5. Limitations
- This patch improves diagnosis only; it does not automatically sanitize user shell environments or unload conflicting site Qt modules.
- Successful interactive launch still depends on installing the optional extras into the same interpreter that runs `python -m skelhub` or the `skelhub` console script.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py tests/test_graph_visualization.py`
- `.venv/bin/python -c "from skelhub.visualization.graph_viewer import _build_optional_dependency_error; print(_build_optional_dependency_error(...))"` to confirm the richer diagnostic output

7. Remaining risks or recommended next steps
- After reinstalling with `python -m pip install -e .[graphviz]`, re-run the viewer with `python -m skelhub graphviz ...`; if the Qt ABI error persists, inspect and trim `LD_LIBRARY_PATH` or unload conflicting Qt environment modules before retrying.

## 2026-04-14 00:00:02 AEST

1. Summary of what changed
- Debugged the `skelhub graphviz` installation failure path and confirmed the main issue was interpreter/environment mismatch rather than a broken extra declaration.
- Improved the graph viewer import guard so missing optional dependencies now report the active interpreter, the specific missing packages, and the correct same-interpreter install command.
- Updated installation guidance to prefer `python -m pip install -e .[graphviz]` and same-interpreter execution so the viewer path is easier to recover in mixed-environment setups.

2. Files added, removed, or modified
- Modified `skelhub/visualization/graph_viewer.py`.
- Modified `tests/test_graph_visualization.py`.
- Modified `README.md`.

3. Architecture decisions made
- Kept the fix focused on the visualization dependency-loading path without changing unrelated CLI or backend behavior.
- Preserved lazy optional imports for Qt while making the failure message environment-aware instead of implying that any editable install should have been sufficient.

4. Assumptions
- The most common failure mode for this command is that users install SkelHub with one interpreter but invoke a different `skelhub` console script from `PATH`.
- Reporting the active interpreter path in the error is acceptable and useful for debugging package-environment mismatches.

5. Limitations
- This patch does not automatically repair broken shell environments; it improves diagnosis and guidance so the user can install extras into the correct interpreter.
- The viewer still requires the optional `graphviz` extras and a desktop-capable environment for the interactive window itself.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py tests/test_graph_visualization.py`
- `.venv/bin/python -m skelhub graphviz --help`

7. Remaining risks or recommended next steps
- After reinstalling with `python -m pip install -e .[graphviz]`, verify that `which skelhub` and `python -c "import sys; print(sys.executable)"` point into the same environment before retrying the command.

## 2026-04-14 00:00:01 AEST

1. Summary of what changed
- Added a lightweight Qt-based GraphML viewer under `skelhub.visualization` for interactive 3D graph inspection.
- Extended the unified CLI with `skelhub graphviz`, including `--edge_thickness` and `--node_size` appearance controls.
- Updated framework-facing documentation and package exports so the viewer is discoverable without changing the existing run or evaluation paths.

2. Files added, removed, or modified
- Added `skelhub/visualization/graph_viewer.py`.
- Modified `skelhub/visualization/__init__.py`, `skelhub/api.py`, `skelhub/__init__.py`, and `skelhub/cli/main.py`.
- Modified `pyproject.toml` to add optional `graphviz` extras for the Qt viewer dependencies.
- Modified `README.md`, `docs/architecture.md`, and `tests/test_framework_cli.py`.
- Added `tests/test_graph_visualization.py`.

3. Architecture decisions made
- Kept GraphML parsing and rendering isolated inside `skelhub.visualization` rather than mixing viewer logic into evaluation or postprocessing code.
- Reused the existing SkelHub GraphML coordinate convention, expecting node attributes `X`, `Y`, and `Z` first, with small compatibility fallbacks for lowercase axes and legacy `v_coords`.
- Made Qt imports lazy and optional so normal package installation and existing CLI commands keep their current behavior unless the viewer is explicitly invoked.

4. Assumptions
- The intended GraphML inputs are SkelHub-generated or SkelHub-compatible graphs that carry explicit 3D node coordinates.
- Adding Qt support as an optional extra is preferable to making GUI dependencies mandatory for all SkelHub users.

5. Limitations
- The interactive window requires optional GUI dependencies from `pip install -e .[graphviz]`.
- The viewer does not attempt automatic layout for graphs missing spatial metadata; it fails with a clear error instead.
- GUI launch behavior was validated through non-interactive loading and CLI smoke coverage in this headless workspace rather than a full windowed manual session.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/cli/main.py skelhub/api.py tests/test_graph_visualization.py tests/test_framework_cli.py`
- `.venv/bin/python -m skelhub graphviz --help`
- `.venv/bin/python -c "..."` smoke check confirming `load_graph_visualization_data()` loads a minimal GraphML file with `X/Y/Z` node coordinates and returns the expected node and edge arrays.
- `.venv/bin/python -c "..."` smoke check confirming `python -m skelhub graphviz --input missing.graphml` exits with code `2` and emits the expected missing-coordinate error.
- Attempted `pytest tests/test_graph_visualization.py tests/test_framework_cli.py`, but the workspace's installed `pytest` stack still fails before test collection with the pre-existing `AttributeError: __spec__` issue in `py`/`pytest`.

7. Remaining risks or recommended next steps
- Run the viewer manually in a desktop-enabled environment after installing the optional Qt extras to confirm the interaction feel and default sizing on real data.

## 2026-04-14 00:00:00 AEST

1. Summary of what changed
- Added a new `lee94` algorithm backend under `skelhub.algorithms.lee94` as a thin framework adapter around `scikit-image`'s Lee-method skeletonization.
- Registered and exposed the new backend through the shared algorithm registry, package exports, framework API, and unified CLI so it can be selected with `skelhub run --algorithm lee94`.
- Added lightweight framework tests and updated docs so SkelHub no longer reads as MCP-only.

2. Files added, removed, or modified
- Added `skelhub/algorithms/lee94/config.py`, `skelhub/algorithms/lee94/backend.py`, and `skelhub/algorithms/lee94/__init__.py`.
- Modified `skelhub/algorithms/__init__.py`, `skelhub/api.py`, and `skelhub/cli/main.py` for package-level exposure and registry-backed execution.
- Modified `skelhub/io/nifti_writer.py` so the unified API path accepts `Path` outputs as advertised.
- Added `tests/test_lee94_backend.py`.
- Modified `tests/test_framework_core.py` and `tests/test_framework_cli.py`.
- Modified `README.md`, `docs/architecture.md`, and `docs/algorithms.md`.

3. Architecture decisions made
- Kept Lee94 backend-specific logic isolated in its own backend package rather than folding thinning behavior into framework core or evaluation code.
- Used the same backend contract as MCP: a backend class with `name`, `build_config`, and `run`, returning a standardized `SkeletonResult`.
- Switched CLI/API registration bootstrap to import `skelhub.algorithms` as a package-level registration point rather than importing only MCP explicitly.

4. Assumptions
- The requested Lee94 backend should operate on the same normalized NIfTI input path already used by the framework.
- Thresholding normalized input at `0.5` is an acceptable minimal config layer for a backend that requires binary foreground input.

5. Limitations
- The Lee94 backend validates only 3D inputs and raises clearly on non-3D volumes.
- In this workspace, the default `python` interpreter does not currently have `scikit-image` installed, so runtime validation had to use an alternate available interpreter.

6. Tests run
- `python -m py_compile ...` over the modified `skelhub/` package and updated test files.
- `conda run -p /scratch/project/simvascmri/conda_envs/vessel_boost python -m skelhub run --algorithm lee94 --input /scratch/user/uqmxu4/Tools/SkelHub/test_data/small_test_data/CLIP_MASKED_sub_160um_seg.nii.gz --output /scratch/user/uqmxu4/Tools/SkelHub/test_outputs/skelhub_lee94_small.nii.gz --verbose`
- `conda run -p /scratch/project/simvascmri/conda_envs/vessel_boost python -m skelhub run --algorithm mcp --input /scratch/user/uqmxu4/Tools/SkelHub/test_data/small_test_data/CLIP_MASKED_sub_160um_seg.nii.gz --output /scratch/user/uqmxu4/Tools/SkelHub/test_outputs/skelhub_mcp_small_regression.nii.gz --min-object-size 1 --verbose`
- Direct framework smoke script covering `list_backends()`, `get_backend("lee94")`, `run_algorithm_from_path(..., algorithm="lee94", ...)`, and output non-emptiness on the bundled small dataset.
- `conda run -p /scratch/project/simvascmri/conda_envs/vessel_boost python -m skelhub run --help` to confirm the CLI advertises both `lee94` and `mcp`.

7. Remaining risks or recommended next steps
- Once a normal `pytest` environment is available, run the full test suite including the new Lee94 tests through the standard runner instead of the current smoke-test path.
- If additional non-MCP backends are added, consider grouping backend-specific CLI arguments more explicitly, but that was intentionally left lightweight in this patch.

## 2026-04-13 17:20:28 AEST

1. Summary of what changed
- Removed the pre-refactor top-level MCP implementation tree: `core/`, `io/`, `utils/`, and the legacy `main.py`.
- Kept the active MCP backend entirely under `skelhub/algorithms/mcp/` and updated tests to import and exercise that package path directly.
- Added a CLI alias so both `--max-iterations` and `--max-iteration` route to the same MCP framework parameter.

2. Files added, removed, or modified
- Removed `core/*.py`, `io/*.py`, `utils/*.py`, and `main.py`.
- Modified `skelhub/cli/main.py` to accept `--max-iteration` as an alias for `--max-iterations`.
- Modified the legacy algorithm tests in `tests/` to import from `skelhub.algorithms.mcp` and to invoke `python -m skelhub` instead of the deleted top-level CLI wrapper.
- Updated `MCP_AGENT.md` and `MCP_ALGORITHM.md` with notes that map their historical path references to the current backend location.

3. Architecture decisions made
- Chose to remove the redundant top-level MCP code completely now that the framework package is the sole supported implementation path.
- Kept MCP-specific runtime logic isolated under `skelhub/algorithms/mcp/` rather than recreating any compatibility shims for the deleted directories.

4. Assumptions
- The requested cleanup was intended to remove the old standalone MCP code tree entirely, not keep duplicate wrapper modules around it.
- The requested command spelling `--max-iteration` should be supported as-is, so I added it as a CLI alias rather than treating it as a user typo.

5. Limitations
- `pytest` is still blocked in this environment by the existing local Python packaging issue (`AttributeError: __spec__` inside the installed `py`/`pytest` stack), so automated test execution still cannot run through the normal test runner here.
- `MCP_AGENT.md` and `MCP_ALGORITHM.md` still describe the historical MCP module layout in detail; they now include mapping notes, but they were not fully rewritten line-by-line in this cleanup pass.

6. Tests run
- `python -m py_compile ...` across the active `skelhub/` package and top-level test modules after the cleanup.
- `/tmp/skelhub_cli_venv/bin/skelhub run --help` to confirm the console entrypoint remains available and exposes the MCP CLI.
- `/tmp/skelhub_cli_venv/bin/skelhub run --algorithm mcp --threshold-scale 1.0 --dilation-factor 2.0 --max-iteration 200 --verbose -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_11.nii -o ./test_outputs/test_11/skhub_11_ts_1_df_2_temp.nii`
- `cmp -s` plus SHA-256 and NIfTI array comparison against `./test_outputs/test_11/skhub_11_ts_1_df_2.nii`

7. Remaining risks or recommended next steps
- Repair the local `pytest` environment so the updated tests can be executed through the normal runner again.
- If these MCP design docs should become fully framework-native references, convert all explicit old-path mentions in `MCP_AGENT.md` and `MCP_ALGORITHM.md` to `skelhub/algorithms/mcp/*` in a future docs pass.

## 2026-04-13 14:50:19 AEST

1. Summary of what changed
- Refactored the repo into an initial SkelHub framework package under `skelhub/` with shared core models, a backend registry, unified CLI entrypoints, and a framework-level evaluation placeholder.
- Integrated the current MCP implementation under `skelhub.algorithms.mcp` using package-safe imports and a thin adapter that returns a shared `SkeletonResult`.
- Kept the refactor non-destructive by retaining the legacy top-level layout and routing `main.py` through the new framework CLI path.

2. Files added, removed, or modified
- Added `pyproject.toml`.
- Added framework package files under `skelhub/cli`, `skelhub/core`, `skelhub/io`, `skelhub/evaluation`, and placeholder namespace packages for future layers.
- Added MCP backend files under `skelhub/algorithms/mcp/` by copying the current implementation into the new backend namespace and fixing imports there.
- Added `docs/architecture.md`, `docs/algorithms.md`, and `docs/evaluation.md`.
- Replaced the top-level `README.md` with a framework-oriented version.
- Modified `main.py` into a compatibility wrapper for `skelhub run --algorithm mcp`.
- Added framework-focused tests in `tests/test_framework_core.py`, `tests/test_framework_cli.py`, and `tests/test_evaluation_placeholder.py`.

3. Architecture decisions made
- Chose a thin backend adapter so MCP-specific orchestration and metadata remain isolated under `skelhub.algorithms.mcp` instead of leaking into the framework core.
- Standardized framework outputs around `VolumeData`, `SkeletonResult`, `GraphResult`, and `EvaluationResult`.
- Exposed the new primary user flow through `skelhub run` and `skelhub evaluate`, while keeping legacy entrypoints available as wrappers for compatibility.

4. Assumptions
- The requested `MCP_AGENTS.md` corresponds to the repository file `MCP_AGENT.md`, because no `MCP_AGENTS.md` file exists in the checkout.
- Preserving MCP behavior means preserving the current implementation path documented in `MCP_ALGORITHM.md`, including the existing safety and reporting behavior.
- Keeping the top-level legacy modules in place is preferable for a non-destructive first refactor, even though the framework package is now the intended primary path.

5. Limitations
- The evaluation subsystem is only a placeholder and does not compute metrics yet.
- The console command `skelhub` is provided through `pyproject.toml`, so it becomes available after package installation; local no-install execution is via `python -m skelhub`.
- Legacy top-level MCP modules are still present for compatibility, so the repo temporarily contains both the framework package and the original layout.

6. Tests run
- `python -m py_compile main.py ...` over the new `skelhub/` package and new framework tests to catch syntax issues after the refactor.
- `python -m skelhub run --algorithm mcp --input /scratch/user/uqmxu4/Tools/SkelHub/test_data/small_test_data/CLIP_MASKED_sub_160um_seg.nii.gz --output /scratch/user/uqmxu4/Tools/SkelHub/test_outputs/skelhub_mcp_small.nii.gz --min-object-size 1 --verbose`
- `python -m skelhub evaluate --pred /scratch/user/uqmxu4/Tools/SkelHub/test_outputs/skelhub_mcp_small.nii.gz`
- `python /scratch/user/uqmxu4/Tools/SkelHub/main.py -i /scratch/user/uqmxu4/Tools/SkelHub/test_data/small_test_data/CLIP_MASKED_sub_160um_seg.nii.gz -o /scratch/user/uqmxu4/Tools/SkelHub/test_outputs/skelhub_mcp_small_legacy.nii.gz --min-object-size 1`
- Direct framework smoke script confirming backend registration, MCP config validation, and evaluation placeholder loading.
- Attempted `pytest` and `python -m pytest` for the new framework tests, but the local Python environment has a broken `pytest` installation (`AttributeError: __spec__` from the installed `py` package shim), so those automated test invocations could not run in this environment.

Test outcomes:

- The framework MCP run completed successfully on the requested small dataset.
- The resulting output NIfTI was non-empty with `50` nonzero voxels and unique values `[0.0, 1.0]`.
- Verbose MCP output reported `1` object and `3` accepted branches.
- The framework evaluation placeholder loaded the produced skeleton and reported success.
- The legacy `main.py` compatibility wrapper also produced an output file successfully.

7. Remaining risks or recommended next steps
- Add metric implementations only after the framework result schema and standardized output conventions settle.
- Decide later whether to retire the legacy top-level MCP modules once downstream users have moved to `skelhub`.
- Repair or replace the local `pytest` environment so the new and legacy test suites can be exercised through their normal runner again.

## Milestone 1

- NIfTI load and save utilities.
- CLI that reads an input volume and writes an output volume unchanged.
- Multi-object decomposition scaffolding and synthetic fixture generation.

## Milestone 2

- FDT computation for binary volumes using `scipy.ndimage.distance_transform_edt`.
- Fuzzy FDT propagation for fuzzy-valued volumes using explicit weighted boundary-to-interior relaxation.
- fCMB detection with 26-neighbour comparisons.
- Non-interactive visualization output for the synthetic straight-tube acceptance check.

## Milestone 3

- LSF computation, with zero response outside the fCMB set and support for strong quench voxel detection via `LSF > 0.5`.
- Geodesic distance computation over object voxels only, using Dijkstra and 26-neighbour Euclidean step lengths.

## Milestone 4

- Minimum-cost path extraction using Dijkstra with 26-neighbour connectivity and the LSF-weighted step-cost from `AGENT.md`.
- Synthetic straight-tube and sharp-corner path verification to confirm the returned voxel path stays inside the object support and follows the expected medial route.

## Milestone 5

- Local scale-adaptive dilation implemented with 26-neighbour Euclidean propagation constrained to the object mask and seeded by `2 * FDT` along a branch.
- Branch significance helper added to sum LSF only over the unmarked portion of a candidate branch.
- Straight-tube acceptance checks added to confirm centreline dilation recovers approximately the full tube cross-section, with a small tolerance for discretisation.

## Milestone 6

- Full end-to-end single-object skeleton extraction implemented in `core/skeleton.py` following Step 8 from `AGENT.md`.
- Single-object subtree discovery added in `utils/connected_components.py` using 26-connected component labelling on `(O - O_marked)`.
- Per-object root detection added in `utils/root_detection.py` with both `max_fdt` and `topmost` strategies.
- Volume-wide orchestration added in `utils/multi_object.py` so disconnected objects are decomposed, skeletonized independently, and merged back together.
- CLI wiring in `main.py` now runs the Milestone 6 pipeline and supports `--verbose` progress reporting.
- Synthetic Milestone 6 acceptance tests now save non-interactive skeleton figures to `outputs/figures_m6/`.

## Milestone 7

- Added an optional `dilation_factor` argument to `core/dilation.py::local_scale_adaptive_dilation()`, `core/skeleton.py::extract_skeleton()`, and `utils/multi_object.py::skeletonize_volume()`, with CLI exposure as `--dilation-factor` in `main.py`.
- Updated the `marked_mask` generation path so the initial root dilation and each accepted-branch dilation can use a configurable scale factor without changing existing callers.
- Preserved the default behavior by keeping the default dilation factor at `2.0`, which matches the prior hard-coded `2 * FDT(p)` rule.
- Profiled the Milestone 6 pipeline and confirmed the main runtime hotspots are the geodesic Dijkstra solve, the minimum-cost path Dijkstra solve, and branch dilation.
- Reduced a major Dijkstra bottleneck in `core/skeleton.py` by computing geodesic distance once per outer iteration instead of once per subtree. This is safe because all subtrees in a given iteration use the same `O_marked`.
- Preserved the existing heap-based wavefront implementation for local scale-adaptive dilation in `core/dilation.py`. It already replaces the naive convergence loop from the paper with an equivalent priority-queue propagation, so no broader rewrite was needed.
- Added `--max-iterations` to `main.py` with default `200` so pathological objects stop safely instead of looping indefinitely.
- Extended verbose runtime reporting so each object now logs its index and label, total iteration count, branches added per iteration, total significant branches detected, and wall-clock runtime.
- Added a final verbose summary across all objects including average iterations per object, total branches, and the reference band `[log2(N), sqrt(N)]` for `N` terminal branches.
- Added Milestone 7 tests to confirm automatic output-directory handling, verbose summary content, and explicit reporting when the iteration cap is reached.
- Investigated a late-iteration stagnation on synthetic acceptance case `test_11`. The diagnosed culprit is a prolonged no-progress phase in the main skeleton-growth loop after weak branch rejection: `O_marked` and the skeleton stop growing, but the loop can remain busy in repeated rejection work instead of exiting promptly.
- Narrowed a separate `test_11` hang to `core/geodesic.py::compute_geodesic_distance()`: the Dijkstra heap could grow pathologically because the relax step compared a higher-precision candidate against a `float32` distance array, allowing repeated re-enqueueing of voxels whose stored distance did not actually improve after assignment.
- Applied the minimal geodesic fix by casting each tentative distance to the array dtype before the relax comparison and heap push, so voxels are only re-enqueued when the stored `float32` distance strictly improves. This preserves the existing algorithm and queue structure while restoring normal heap draining.
- Tried a subtree-local alternate-candidate fix for rejected branches, but did not keep it because it changed late-phase behaviour without giving a reliable clean completion in this environment.
- Added a progress-based active safety fuse in `core/skeleton.py` as a fallback safeguard. After each accepted branch, the fuse is reset. If there is no skeleton-growth progress for `10s`, it arms a `60s` countdown. If progress still does not resume, it interrupts the current object safely, keeps the partial skeleton as-is, and logs that the output may be incomplete.
- Re-ran `python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_11.nii -o ./test_outputs/skel_m7_synthetic_11.nii.gz --verbose` after adding the fuse. Object 1 hit the fuse during the late no-progress phase, exited safely with a partial skeleton warning, object 2 completed normally, and the overall command finished without error.
- Re-ran `python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_11.nii -o ./test_outputs/skel_m7_synthetic_11.nii.gz --verbose` after the geodesic fix. The command completed normally, `compute_geodesic_distance()` no longer trapped execution in a runaway heap-growth phase, both objects finished, and the clock fuse did not trigger.

## Development Notes

Refresh the synthetic test inputs:

```bash
python tests/fixtures/generate_fixtures.py
```

Run the Milestone 2 and Milestone 3 tests:

```bash
pytest tests/test_distance_transform.py tests/test_maximal_balls.py tests/test_lsf.py tests/test_geodesic.py
```

Run the Milestone 4 tests:

```bash
pytest tests/test_path_cost.py
```

Run the Milestone 5 tests:

```bash
pytest tests/test_skeleton.py
```

Run the Milestone 6 synthetic acceptance tests:

```bash
pytest tests/test_skeleton.py tests/test_multi_object.py
```

Run the Milestone 7 reporting and safety-cap tests:

```bash
pytest tests/test_skeleton.py tests/test_multi_object.py tests/test_milestone7.py
```

Run the broader acceptance checks:

```bash
pytest
```

The Milestone 2 visualization tests save images to `outputs/milestone2/`. These figures show the straight-tube input object, the FDT slice, and the fCMB mask overlaid for quick inspection in non-interactive environments.

`compute_fdt` accepts either binary inputs or fuzzy membership volumes in `[0, 1]`. For binary inputs it uses the EDT fast path. For fuzzy inputs it uses an explicit weighted shortest-path propagation from the object boundary, rather than thresholding the data to binary.

`compute_lsf(volume, fdt)` implements the paper's local significance factor equation over the full 26-neighbourhood. It measures how strongly a voxel behaves like a collision point of independent fronts; the result is constrained to zero outside the fCMB set, and `LSF > 0.5` identifies strong quench voxels.

`compute_geodesic_distance(object_mask, source_mask)` computes purely geometric geodesic distance within the object support using Dijkstra's algorithm. It uses Euclidean 26-neighbour step lengths (`1`, `sqrt(2)`, `sqrt(3)`) and leaves voxels outside the object, or unreachable object voxels, at `np.inf`.

To regenerate the visualization outputs manually:

```bash
pytest tests/test_distance_transform.py tests/test_maximal_balls.py
ls outputs/milestone2
```

The Milestone 6 synthetic acceptance figures are written to `outputs/figures_m6/`. They include:

- `y_tube_overlay.png`
- `y_tube_noisy_overlay.png`
- `two_tubes_overlay.png`

Run the real-data Milestone 6 acceptance command:

```bash
python main.py -i ./test_data/smaller_patch_160/CLIP_MASKED_sub_160um_seg.nii.gz -o ./outputs/skel_m6.nii.gz --verbose
```

This writes the real-data skeleton output to `outputs/skel_m6.nii.gz`. The verbose log reports the number of objects found, per-object branch acceptance progress, and the final skeletal branch count.

Milestone 7 verbose output adds:

- per-object `iterations=...`
- per-object `branches_added_per_iteration=[...]`
- per-object `total_branches=...`
- per-object `time=...s`
- final `average_iterations_per_object=...`
- final `complexity_band=[log2(N)=..., sqrt(N)=...]`

Run the Milestone 7 synthetic acceptance commands:

```bash
python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_11.nii -o ./test_outputs/skel_m7_synthetic_11.nii.gz --verbose
python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_12.nii -o ./test_outputs/skel_m7_synthetic_12.nii.gz --verbose
python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_13.nii -o ./test_outputs/skel_m7_synthetic_13.nii.gz --verbose
```

Run the Milestone 7 real-data acceptance command:

```bash
python main.py -i ./test_data/bigger_patch/bigCLIP_MASKED_sub_160um_seg.nii.gz -o ./test_outputs/skel_m7.nii.gz --verbose
```

Profiling summary:

- Before the Milestone 7 loop change, the noisy synthetic Y-tube profile spent about `0.126s` in `compute_geodesic_distance`, `0.120s` in dilation, and `0.087s` in minimum-cost path extraction during a `~1.50s` end-to-end cProfile run.
- After the change, the same profile spent about `0.125s` in `compute_geodesic_distance`, `0.123s` in dilation, and `0.088s` in minimum-cost path extraction during a `~1.40s` end-to-end cProfile run, while preserving the Milestone 6 branch outputs.
- The key improvement is algorithmic scaling: geodesic distance is no longer recomputed redundantly for every subtree within the same iteration, which matters much more on larger multi-subtree objects than on the small synthetic fixture.

## Paper/Algorithm Comparison (2026-04-01)

Compared sources:

- `ALGORITHM.md` (repository workflow documentation)
- `1-s2.0-S0167865515001063-main.pdf` (Pattern Recognition Letters 76 (2016) 32-40)
- Current implementation in `core/` + `utils/` + `main.py`

Discrepancies found:

- MCP step-cost denominator form differs from the paper equation.
	- Paper Eq. (6) is written as: `SC(p,q) = |p-q| / (epsilon + (average(LSF(p), LSF(q)))^2)`.
	- Implementation in `core/path_cost.py` uses: `SC(p,q) = |p-q| / (epsilon + average_lsf)^2`.
	- This changes the numerical weighting unless `epsilon` is negligible.

- CLI default dilation factor does not match the documented/paper-consistent seed scale.
	- Paper Section 2.3 and `ALGORITHM.md` describe branch dilation seeded by `2 * FDT(p)`.
	- Implementation supports a configurable factor (intentional extension), but `main.py` currently sets `--dilation-factor` default to `1.5` while the help text says `Default: 2.0`.
	- Net effect: running CLI with defaults does not follow the documented default rule.

- Additional stopping criteria exist in code but not in the paper algorithm.
	- Paper termination is based on: full object coverage, or no significant branch from remaining strong quench voxels.
	- Implementation adds `--max-iterations` hard cap and a time-based safety fuse in `core/skeleton.py`.
	- This is a workflow discrepancy from the paper (an engineering safeguard), and can terminate with partial skeleton in pathological cases.

No discrepancy found in these core parts:

- fCMB inequality form and 26-neighbour use.
- LSF definition and strong-quench criterion (`LSF > 0.5`).
- Multi-branch-per-iteration subtree strategy.
- Branch significance accumulation over unmarked region and scale-adaptive threshold base form `3 + 0.5 * FDT(p_v)` (code applies optional multiplier `threshold_scale`, default `1.0`).
