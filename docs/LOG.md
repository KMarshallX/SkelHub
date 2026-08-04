# Development Log

## 2026-08-04 17:41 AEST

### Preserve degree-2 nodes as merged centreline points

1. Summary of what changed
- Added `scripts/protograph_cleaner.sh` with required `--input/-i` and
  `--output/-o` arguments plus optional `--verbose/-v` node progress.
- Contracted maximal degree-2 chains while concatenating their existing float
  and discrete centreline paths, so every removed node position remains in the
  merged edge geometry.
- Added an interactive overwrite prompt and atomic output replacement.
- Preserved distinct parallel paths rather than collapsing edges that share
  retained endpoints.

2. Files added or modified
- Added `skelhub/postprocessing/protograph_cleaner.py`,
  `scripts/protograph_cleaner.sh`, and local regression coverage in
  `tests/test_protograph_cleaner.py`; the repository's existing test-ignore
  policy was not changed.
- Modified `README.md`, `scripts/README.md`, `docs/architecture.md`,
  `docs/postprocessing.md`, `docs/StructuredOutput.md`, and `docs/LOG.md`.

3. Architecture decisions made
- Kept GraphML transformation and validation in the postprocessing layer and
  made the requested Bash script a thin active-environment launcher.
- Used igraph's multigraph support so two vessel paths with the same endpoints
  remain distinct.
- Regenerated merged edge IDs and component-local edge indices while retaining
  unchanged endpoint-node and consistent component metadata.
- Wrote to a temporary sibling file before replacing the destination, so a
  cleaning or GraphML-write failure cannot leave a partial requested output.

4. Assumptions
- `voxel_pos` is the node position contract and `centerline_voxel_points`
  contains an ordered JSON path whose endpoints match its incident nodes.
- If present, `centerline_voxels` is an ordered integer path with the same
  endpoint convention.
- Removed-node radius and identifier values are not required as point metadata;
  only their positions are retained, as requested.

5. Limitations
- Input must be undirected and contain at least one degree-2 node.
- A closed component made entirely from degree-2 nodes retains one anchor and
  becomes a self-loop because GraphML cannot store an edge without a node.
- Downstream tools must support GraphML parallel edges to retain every path.
- Loading and writing use igraph's in-memory GraphML representation.

6. Tests run
- `bash -n scripts/protograph_cleaner.sh`
- `python -m py_compile skelhub/postprocessing/protograph_cleaner.py tests/test_protograph_cleaner.py`
- `python -m pytest -q tests/test_protograph_cleaner.py` (`5 passed`)
- `python -m pytest -q` (`36 passed`)
- Full-file smoke run on
  `test_data/exvivo/Aug/skel_vessyn_aug_protograph.graphml`, including GraphML
  round-trip and centreline integrity checks.
- `git diff --check`

7. Remaining risks or recommended next steps
- Consumers that assume a simple graph should be checked before using cleaner
  output containing parallel paths.
- Add a unified `skelhub` CLI command later if this helper becomes a primary
  postprocessing workflow rather than a focused script.

## 2026-08-02 18:00 AEST

### Preserve continuous Laplacian graph-original edge paths

1. Summary of what changed
- Added `centerline_voxel_points` to every edge in Laplacian
  `--graph_original` GraphML.
- Stored unrounded, unclipped float samples along each straight source-to-target
  segment, including both exact node positions.
- Kept cleaned `--graph_output`, discrete `centerline_voxels`, and NIfTI
  rasterization behavior unchanged.

2. Files added or modified
- Modified `skelhub/algorithms/laplacian/graphml.py` and
  `skelhub/algorithms/laplacian/backend.py`.
- Added local regression coverage in `tests/test_laplacian_graphml.py`; the
  repository's existing test-ignore policy was not changed.
- Modified `docs/algorithms.md`, `docs/postprocessing.md`,
  `docs/StructuredOutput.md`, and `docs/LOG.md`.

3. Architecture decisions made
- Made continuous-path export an explicit writer option enabled only for
  `graph_original`, because both Laplacian GraphML outputs share one writer.
- Used straight per-edge geometry as the canonical contracted-graph
  representation; quadratic Bezier interpolation remains a separate NIfTI
  rasterization rule.
- Sampled a non-degenerate edge with
  `ceil(max(abs(end - start))) + 1` points and stored a zero-length edge as one
  point.

4. Assumptions
- Edge order runs from the exported source node to the exported target node.
- JSON float arrays provide adequate round-trip precision for GraphML edge
  metadata.

5. Limitations
- `centerline_voxel_points` is voxel-space only and does not add world-space
  edge samples.
- Feature extraction continues to use discrete `centerline_voxels`.
- The continuous straight path intentionally differs from the quadratic-Bezier
  rule used around degree-2 nodes when rasterizing the skeleton NIfTI.

6. Tests run
- `python -m py_compile skelhub/algorithms/laplacian/graphml.py skelhub/algorithms/laplacian/backend.py tests/test_laplacian_graphml.py`
- `python -m pytest -q tests/test_laplacian_graphml.py tests/test_crop_escaping_graph_patches.py`
  (`8 passed`)
- `python -m pytest -q` (`31 passed`)
- CLI smoke run using `tests/fixtures/straight_tube.nii.gz` with both GraphML
  outputs, confirming the new field is present only in `graph_original` and
  preserves float endpoints after an igraph GraphML round trip.
- `git diff --check`

7. Remaining risks or recommended next steps
- Add affine-transformed `centerline_points` later only if world-space edge
  paths become part of the shared GraphML contract.

## 2026-07-29 16:59 AEST

### Report local PCA eigenvalue ratios

1. Summary of what changed
- Added `lambda_1/lambda_2`, `lambda_2/lambda_3`, and
  `lambda_1/lambda_3` to both coordinate-system reports.
- Reported a ratio as `inf` when its denominator is zero or numerically near
  zero.
- Updated references after the shell entrypoint was renamed to
  `run_local_pca.sh`.

2. Files added or modified
- Modified `scripts/run_local_pca.py`.
- Modified `tests/test_run_local_pca.py`.
- Modified `scripts/README.md` and `docs/LOG.md`.

3. Architecture decisions made
- Reused the PCA report's scale-relative numerical-rank tolerance to identify
  effectively zero ratio denominators.

4. Assumptions
- `lambda_1`, `lambda_2`, and `lambda_3` refer to eigenvalues in descending
  order.

5. Limitations
- Very small nonzero denominator eigenvalues within the numerical tolerance
  are intentionally represented as `inf`.

6. Tests run
- `bash -n scripts/run_local_pca.sh`
- `python -m py_compile scripts/run_local_pca.py tests/test_run_local_pca.py`
- `python -m pytest -q` (`28 passed`)
- Reference-data smoke run confirming finite `lambda_1/lambda_2` and `inf`
  for ratios divided by the numerically zero `lambda_3`.
- `git diff --check`

7. Remaining risks or recommended next steps
- None identified.

## 2026-07-29 15:50 AEST

### Add local vessel-node PCA report

1. Summary of what changed
- Added `scripts/run_local_pca.sh` for local PCA of a quoted GraphML node list.
- Added separate world-coordinate and voxel-coordinate scatter matrices and
  descending eigendecomposition reports.
- Added input validation and non-fatal degeneracy warnings.
- Documented the script interface and numerical convention.

2. Files added or modified
- Added `scripts/run_local_pca.sh` and `scripts/run_local_pca.py`.
- Added `tests/test_run_local_pca.py`.
- Modified `scripts/README.md` and `docs/LOG.md`.

3. Architecture decisions made
- Kept the shell entrypoint thin and placed GraphML parsing and numerical work
  in a testable Python helper.
- Used `C = sum((x - mean) (x - mean)^T)` directly, without division by `N` or
  `N-1`.
- Used `numpy.linalg.eigh` for the symmetric scatter matrix and reversed its
  ascending output to report the largest eigenvalue first.

4. Assumptions
- World coordinates are stored as node attributes `X`, `Y`, and `Z`.
- Voxel coordinates are stored as a three-value JSON array in `voxel_pos`.
- Selected nodes do not need to form a connected subgraph.

5. Limitations
- Raw `numpy.linalg.eigh` eigenvectors are already unit length, so raw and
  explicitly normalized vectors normally match.
- Eigenvector signs are arbitrary and are not made deterministic.

6. Tests run
- `bash -n scripts/run_local_pca.sh`
- `python -m py_compile scripts/run_local_pca.py tests/test_run_local_pca.py`
- `python -m pytest -q tests/test_run_local_pca.py` (`5 passed`)
- `python -m pytest -q` (`28 passed`)
- Reference-data smoke run with `component_0001_my_0729.graphml` and nodes
  `[n190, n191, n248]`.
- `git diff --check`

7. Remaining risks or recommended next steps
- None identified.

## 2026-07-27 19:59 AEST

### Improve graphviz overlay filename visibility

1. Summary of what changed
- Split the overlay top bar into separate Base and Overlay filename lines.
- Added continuous scrolling for overflowing top-bar filenames.
- Added hover-only scrolling for overflowing filenames in open file dropdown
  rows.
- Expanded filename text to use the available width of the View Layout
  selectors and their matching menu rows.
- Vertically centered both overlay-header text rows inside the bordered top
  bar.

2. Files added or modified
- Modified `.gitignore`.
- Modified `skelhub/visualization/_graph_viewer_impl.py`.
- Modified the visualization facade modules for constants, layout, session,
  and interaction helpers.
- Added `tests/test_graphviz_filename_marquee.py`.
- Modified `docs/visualization.md` and `docs/LOG.md`.

3. Architecture decisions made
- Updated existing 2D text actors from one shared repeating UI timer so
  filename motion does not rebuild visualization geometry or the full Tools
  panel.
- Used VTK vertical text justification for header alignment and separated the
  dropdown arrow from the filename so it does not reduce the visible label.
- Kept marquee state in the viewer session and confined all behavior to the
  visualization subsystem.

4. Assumptions
- “Rolling” means cyclic leftward marquee motion.
- Dropdown animation applies to overflowing rows in an open file-selection
  menu; closed selector fields remain ellipsized.

5. Limitations
- Overflow detection uses the viewer's existing conservative character-width
  estimate rather than font-specific pixel measurement.
- Desktop visual review is still recommended on the target VTK backend.

6. Tests run
- `python -m pytest -q` (`23 passed`)
- `python -m py_compile skelhub/visualization/_graph_viewer_impl.py
  skelhub/visualization/constants.py skelhub/visualization/layout.py
  skelhub/visualization/session.py skelhub/visualization/interaction.py
  skelhub/visualization/controls.py`
- `git diff --check`
- Off-screen VTK smoke renders for the two-line overlay header and widened
  open Base-file menu, including vertical-boundary inspection.

7. Remaining risks or recommended next steps
- Confirm the 180 ms scroll speed feels comfortable on the target display.

## 2026-07-27 19:34 AEST

### Report connectivity-aware component counts

1. Summary of what changed
- Added `--connectivity` / `-c` to `scripts/checker.sh`, accepting 6, 18, or 26
  and defaulting to 26.
- Added foreground and skeleton connected-component counts to the checker
  report using the selected connectivity.
- Expanded checker regression coverage and usage documentation.

2. Files added or modified
- Modified `.gitignore` to include the checker regression test.
- Modified `scripts/checker.sh`.
- Modified `tests/test_checker.py`.
- Modified `scripts/README.md`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Used SciPy's 3D binary neighborhood structures for standard 6-, 18-, and
  26-connectivity and applied the same structure to both volumes.

4. Assumptions
- Checker inputs are 3D volumes because the supported connectivity choices are
  defined for 3D voxel neighborhoods.

5. Limitations
- The checker does not resample volumes or reconcile differing spatial
  metadata.

6. Tests run
- `bash -n scripts/checker.sh`
- `python -m pytest -q tests/test_checker.py` (`7 passed`)
- `git diff --check`

7. Remaining risks or recommended next steps
- None identified.

## 2026-07-27 15:19 AEST

### Rasterize escaping Laplacian graph patches

1. Summary of what changed
- Added `--rasterization` to `crop_escaping_graph_patches.sh`.
- Reintroduced `--skel-path` only as the required destination for enabled
  graph-patch rasterization; `--input-skel` remains removed.
- Rasterized both primary and optional secondary GraphML patches with the same
  graph rule used for Laplacian `--output`.
- Added parser and two-graph end-to-end regression coverage.

2. Files added or modified
- Modified `.gitignore`.
- Modified `scripts/crop_escaping_graph_patches.sh`.
- Modified `scripts/crop_escaping_graph_patches.py`.
- Modified `scripts/README.md`.
- Modified `tests/test_crop_escaping_graph_patches.py`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Reused `GeometricGraph` and `rasterize_graph_26conn` from the Laplacian
  backend instead of duplicating its interpolation and connectivity rules.
- Rasterized in the original component bbox, matching Laplacian backend
  clipping, then embedded the result in the buffered patch space.
- Used `graph_...nii.gz` and `graph2_...nii.gz` prefixes to keep rasterized
  outputs paired unambiguously with their GraphML patches.

4. Assumptions
- Input GraphML files use the Laplacian schema with JSON `voxel_pos` and
  positive integer `component_label` vertex attributes.
- `--input-graph2`, when provided, should be rasterized alongside
  `--input-graph`.

5. Limitations
- Rasterization is specifically the Laplacian backend rule; arbitrary GraphML
  schemas are not supported.
- Runs without escaping primary-graph nodes still return before creating any
  patch output directories.

6. Tests run
- `pytest -q tests/test_crop_escaping_graph_patches.py`
- Real-data equivalence check against the component-label-1 crop of the
  Laplacian `--output`.
- `bash -n scripts/crop_escaping_graph_patches.sh`
- `python -m py_compile scripts/crop_escaping_graph_patches.py`
- Wrapper `--help` smoke test.
- `git diff --check`

7. Remaining risks or recommended next steps
- External callers that enable `--rasterization` must provide `--skel-path`.

## 2026-07-27 15:06 AEST

### Remove skeleton cropping from escaping-graph patches

1. Summary of what changed
- Removed skeleton NIfTI patch cropping from
  `scripts/crop_escaping_graph_patches.py`.
- Removed the `--input-skel` and `--skel-path` command-line options.
- Updated the script documentation and added regression coverage for the
  removed options.

2. Files added or modified
- Modified `.gitignore` to include the new focused regression test.
- Modified `scripts/crop_escaping_graph_patches.py`.
- Modified `scripts/README.md`.
- Added `tests/test_crop_escaping_graph_patches.py`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Retained raw bounding-box NIfTI cropping only for the optional intensity
  image workflow.
- Removed the old options instead of keeping deprecated aliases, so unsupported
  skeleton-cropping requests fail during argument parsing.

4. Assumptions
- Existing callers using `--input-skel` or `--skel-path` should be updated
  rather than supported through a compatibility period.

5. Limitations
- The helper does not produce any skeleton patch output.

6. Tests run
- `pytest -q tests/test_crop_escaping_graph_patches.py`
- `bash -n scripts/crop_escaping_graph_patches.sh`
- `python -m py_compile scripts/crop_escaping_graph_patches.py`
- `git diff --check`

7. Remaining risks or recommended next steps
- External scripts outside this repository that pass either removed option must
  remove those arguments.

## 2026-07-22 22:38 AEST

### Split crop patch output directories

1. Summary of what changed
- Updated `scripts/crop_escaping_graph_patches.py` so `--nif-path` stores only
  cropped foreground NIfTI patches.
- Added `--skel-path` and made it required when `--input-skel` is provided.
- Added `--img-path` and made it required when `--input-img` is provided, so
  image crops no longer share the foreground directory.
- Added yellow terminal warnings before creating missing output directories and
  clear failures if a directory cannot be created.

2. Files modified
- `scripts/crop_escaping_graph_patches.py`
- `scripts/README.md`
- `docs/LOG.md`

3. Architecture decisions made
- Kept foreground, skeleton, image, and graph patch outputs in separate
  directory roles.
- Implemented directory validation inside the Python helper because it owns the
  parsed output paths and writes the patch files.

4. Assumptions
- `--input-img` should follow the same separated-output rule as `--input-skel`
  because `--nif-path` is now foreground-only.

5. Limitations
- Directory creation warnings are emitted only when patches need to be written;
  runs with no escaping graph nodes still exit before creating output paths.

6. Tests run
- `bash -n scripts/crop_escaping_graph_patches.sh`
- `python -m py_compile scripts/crop_escaping_graph_patches.py`
- Lightweight parser/directory smoke test with stubbed optional imaging
  dependencies, covering required `--skel-path`, required `--img-path`, and
  yellow warning directory creation.
- `git diff --check`

7. Remaining risks or recommended next steps
- None identified.

## 2026-07-22 22:28 AEST

### Use conda environment for crop patch wrapper

1. Summary of what changed
- Removed the hard requirement for `scripts/crop_escaping_graph_patches.sh` to
  source the repository `.venv`.
- Added validation that the currently active conda environment has `python` and
  the crop helper's required packages before running.
- Added a clear missing-package report for `igraph`, `nibabel`, `numpy`, and
  `scipy`.

2. Files modified
- `scripts/crop_escaping_graph_patches.sh`
- `scripts/README.md`
- `docs/LOG.md`

3. Architecture decisions made
- Kept dependency validation in the shell wrapper so the Python helper remains
  focused on cropping and graph processing.
- Checked only the packages imported directly by
  `crop_escaping_graph_patches.py`.

4. Assumptions
- The intended execution path is an activated conda environment, matching the
  newer SkelHub helper scripts.

5. Limitations
- The wrapper verifies imports, not exact package versions.

6. Tests run
- `bash -n scripts/crop_escaping_graph_patches.sh`
- `env CONDA_PREFIX=/tmp/skelhub-test-conda CONDA_DEFAULT_ENV=skelhub-test ./scripts/crop_escaping_graph_patches.sh --help`, confirming missing packages are listed before exit in the current shell.
- `git diff --check`

7. Remaining risks or recommended next steps
- None.

## 2026-07-21 17:25 AEST

### Add foreground confinement checker

1. Summary of what changed
- Added `scripts/checker.sh` to check whether every nonzero skeleton voxel is
  located in a nonzero foreground voxel.
- Added argument, extension, file, dependency, NIfTI loading, and shape
  validation.
- Added reporting for sorted unique values other than zero and one while still
  treating every nonzero value as foreground or skeleton.

2. Files added or modified
- Added `scripts/checker.sh`.
- Added `tests/test_checker.py`.
- Modified `scripts/README.md`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Kept the checker as an isolated helper script and used the project's existing
  NumPy and NiBabel dependencies for NIfTI access.
- Reserved stdout for the final `Yes` or `No`; diagnostics and non-binary value
  reports use stderr.

4. Assumptions
- Voxel confinement is an index-wise comparison, so matching shapes are
  required but affine equivalence is not.
- A `No` result is a successful check and therefore exits with status zero;
  invalid inputs exit with status two.

5. Limitations
- The script does not resample volumes or reconcile differing spatial metadata.

6. Tests run
- `bash -n scripts/checker.sh`
- `python -m pytest tests/test_checker.py -q` (`4 passed`), covering confined
  and escaping skeletons, non-binary value reporting and inclusion, and
  mismatched shapes.
- `python -m pytest -q` (`10 passed`).
- `git diff --check`

7. Remaining risks or recommended next steps
- None.

## 2026-07-21 16:14 AEST

### Document MCP parameter tuning effects

1. Summary of what changed
- Expanded every entry under `MCP Backend` > `Parameters` in
  `docs/algorithms.md` with its larger/smaller or enabled/disabled tuning
  effects immediately after the default value.
- Clarified the behavioral difference between the categorical `max_fdt` and
  `topmost` root methods.

2. Files modified
- `docs/algorithms.md`
- `docs/LOG.md`

3. Architecture decisions made
- Documented behavior from the current MCP implementation without changing its
  configuration schema or runtime behavior.

4. Assumptions
- Array-axis orientation is dataset-dependent, so `topmost` is described in
  array coordinates rather than as a universal anatomical superior direction.

5. Limitations
- Tuning effects describe expected tradeoffs; exact skeleton changes remain
  dependent on object geometry, image quality, and foreground connectivity.

6. Tests run
- Cross-checked descriptions against MCP root selection, branch acceptance,
  dilation, iteration limiting, component filtering, and output merging code.
- Local documentation audit confirmed all seven MCP parameter entries include
  defaults and tuning behavior.
- `git diff --check`

7. Remaining risks or recommended next steps
- None.

## 2026-07-21 16:04 AEST

### Show configured defaults in all CLI help

1. Summary of what changed
- Updated the top-level SkelHub CLI and every subcommand parser to append each
  optional argument's configured default to its `--help` description.
- Applied the same formatter to dynamically selected `skelhub run` backend
  arguments.

2. Files modified
- `skelhub/cli/main.py`
- `docs/LOG.md`

3. Architecture decisions made
- Centralized help formatting in one private `ArgumentParser` subclass so new
  subcommands inherit the behavior automatically.

4. Assumptions
- Required arguments do not need a displayed default because argparse does not
  use their implicit `None` value when they are omitted.
- Optional `None` and boolean defaults should be displayed because they describe
  real command behavior when the option is omitted.

5. Limitations
- Defaults are shown for the backend selected by `--algorithm`; `skelhub run
  --help` without an algorithm continues to show only the common run options.

6. Tests run
- Local parser audit covering `evaluate`, `graphgen`, `feature`, `graphviz`,
  and `run` help for all six registered backends.
- `python -m skelhub evaluate --help`
- `python -m skelhub run --algorithm l1_skeleton --help`
- `python -m py_compile skelhub/cli/main.py`
- `python -m pytest -q` (`6 passed`)
- `git diff --check`

7. Remaining risks or recommended next steps
- None.

## 2026-07-21 14:26 AEST

### Fix graphviz drop-event filename handling

1. Summary of what changed
- Updated `skelhub graphviz` to consume the `vtkStringArray` call-data payload
  carried by VTK `DropFilesEvent` notifications.
- Kept the previous caller-based filename extraction as a compatibility
  fallback and retained support for `.graphml`, `.nii`, and `.nii.gz`.
- Used focused local tests for filename extraction and observer dispatch.

2. Files added or modified
- Modified `skelhub/visualization/_graph_viewer_impl.py`.
- Modified `docs/visualization.md`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Registered the callback on the underlying VTK interactor so VTK's Python
  `calldata_type` annotation is preserved instead of being hidden by the
  PyVista observer wrapper.
- Kept drop handling within the visualization interaction layer and reused the
  existing standardized visualization-file loader.

4. Assumptions
- VTK `DropFilesEvent` supplies a `vtkStringArray` when the active desktop
  backend supports operating-system file drops.

5. Limitations
- Standalone VTK/PyVista backends that do not emit operating-system drop events
  still require the existing `Import` button.
- A live desktop drop cannot be exercised in the headless test environment.

6. Tests run
- `python -m pytest tests/test_graph_visualization_drop.py -q` (`2 passed`)
- `python -m pytest -q` (`6 passed`)
- `python -m py_compile skelhub/visualization/_graph_viewer_impl.py tests/test_graph_visualization_drop.py`
- `python -m skelhub graphviz --help`
- `git diff --check`

7. Remaining risks or recommended next steps
- Confirm one live file drop on each supported desktop backend when available.

## 2026-07-07 12:30 AEST

### Add batch feature extraction script

1. Summary of what changed
- Added `scripts/run_featext.sh` to recursively match foreground NIfTI,
  skeleton NIfTI, and GraphML inputs and call `skelhub feature` for each set.
- Added flat edge/node CSV output naming, verbose progress, environment and
  directory validation, and fail-fast handling for ambiguous or invalid sets.
- Documented the script and added shell-level subprocess coverage.

2. Files added or modified
- Added `scripts/run_featext.sh`.
- Added `tests/test_run_featext.py`.
- Modified `scripts/README.md`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Kept feature calculation in the existing unified `skelhub feature` CLI; the
  new script only handles batch discovery, matching, and orchestration.
- Preferred exact foreground/skeleton stem matches before unique containing
  matches, then required an exact skeleton/GraphML stem match.
- Rejected duplicate foreground stems because flat output directories would
  otherwise overwrite results within one batch.

4. Assumptions
- Feature analysis outputs are the CSV files produced by `skelhub feature`, not
  `.xlsx` workbooks.
- Existing destination CSVs may be replaced.
- Either an activated conda environment or Python virtual environment is valid.

5. Limitations
- Matching is global by basename stem and does not use relative directories.
- Processing is sequential and fail-fast, so an error can leave outputs from
  earlier image sets in place.

6. Tests run
- `bash -n scripts/run_featext.sh`
- `python -m pytest tests/test_run_featext.py -q` (`4 passed`)
- `shellcheck scripts/run_featext.sh` was not run because `shellcheck` is not
  installed in the current environment.

7. Remaining risks or recommended next steps
- Run `shellcheck scripts/run_featext.sh` when the tool is available.

## 2026-06-29 17:55 AEST

### Document postprocessing methods

1. Summary of what changed
- Added concise `Method` workflows for GraphML graph generation and vessel
  feature extraction.

2. Files modified
- `docs/postprocessing.md`
- `docs/LOG.md`

3. Architecture decisions made
- Documented the existing implementation without changing interfaces or
  behavior.

4. Assumptions
- The code in `skelhub/postprocessing/graphgen/` and
  `skelhub/postprocessing/feature/` is the source of truth.

5. Limitations
- The method summaries describe the current workflows rather than their Voreen
  provenance or mathematical derivation.

6. Tests run
- Documentation structure and subsection word counts were checked locally.

7. Remaining risks or recommended next steps
- None; this is a documentation-only change.

## 2026-06-05 23:51 AEST

### Refactor graphviz module import structure

1. Summary of what changed
- Preserved the existing PyVista graph viewer implementation in `skelhub/visualization/_graph_viewer_impl.py`.
- Replaced `skelhub/visualization/graph_viewer.py` with a compatibility facade that re-exports all previous top-level names, including private helpers.
- Added focused visualization modules for constants, models, loading, session state, scene rendering, layout, camera behavior, controls, interaction, and launcher entrypoints.
- Added focused refactor API tests covering legacy imports, package exports, loaders, session behavior, and CLI graphviz dispatch.

2. Files added, removed, or modified
- Added `skelhub/visualization/_graph_viewer_impl.py`.
- Added `skelhub/visualization/constants.py`.
- Added `skelhub/visualization/models.py`.
- Added `skelhub/visualization/loading.py`.
- Added `skelhub/visualization/session.py`.
- Added `skelhub/visualization/scene.py`.
- Added `skelhub/visualization/layout.py`.
- Added `skelhub/visualization/camera.py`.
- Added `skelhub/visualization/controls.py`.
- Added `skelhub/visualization/interaction.py`.
- Added `skelhub/visualization/launcher.py`.
- Modified `skelhub/visualization/graph_viewer.py`.
- Added `tests/test_graph_viewer_refactor_api.py`.
- Modified `docs/architecture.md`.
- Modified `docs/LOG.md`.

3. Architecture decisions made
- Kept `skelhub.visualization.graph_viewer` as the stable legacy facade so existing direct imports continue to work.
- Used grouped module re-exports over the preserved runtime implementation to avoid changing UI rendering, camera, loading, or interaction behavior during this maintainability refactor.
- Added no new dependencies and did not alter CLI arguments, defaults, labels, validation messages, or viewer behavior.

4. Assumptions
- Compatibility includes all names currently importable from `skelhub.visualization.graph_viewer`, including private helper names.
- A conservative mechanical split is preferable here because the graph viewer has dense cross-calls between layout, controls, interaction, rendering, and camera code.

5. Limitations
- The focused modules currently provide organized import surfaces over the preserved runtime implementation; future work can move function bodies module-by-module once behavior tests and desktop smoke coverage are stronger.
- Manual desktop verification is still required for the interactive PyVista window because the current environment does not have the project runtime dependencies installed.

6. Tests run
- `python -m py_compile skelhub/visualization/*.py skelhub/cli/main.py skelhub/api.py`
- `python -m py_compile skelhub/visualization/*.py skelhub/cli/main.py skelhub/api.py tests/test_graph_viewer_refactor_api.py`
- `/usr/bin/python3.12 -m py_compile skelhub/visualization/*.py skelhub/cli/main.py skelhub/api.py tests/test_graph_viewer_refactor_api.py`
- `python -m pytest tests/test_graph_viewer_refactor_api.py -q` could not run because the local Python 3.13 pytest installation fails before collection (`AttributeError: __spec__` in `py/_vendored_packages/apipkg`).
- `python -m skelhub graphviz --help` could not run because `numpy` is not installed in the active Python environment.
- Direct Python import smoke checks could not run because importing `skelhub` also fails before visualization imports with missing `numpy`.

7. Remaining risks or recommended next steps
- Run `python -m pytest tests/test_graph_viewer_refactor_api.py -q` in an environment with working pytest and project dependencies installed.
- Run `python -m skelhub graphviz --help` and manually smoke-test empty, GraphML, NIfTI, double-view, overlay, import, close, reset, fit preview, interactive selection, and camera sync workflows in a desktop-capable environment.

## 2026-06-03 23:42 AEST

### Fix overlay Interactive selected-node highlight

1. Summary of what changed
- Overlay rendering no longer disables Interactive mode or clears the selected node on every overlay scene rebuild.
- Overlay mode now redraws the selected-node highlight after Base/Overlay layers are rebuilt.
- The highlight uses the existing `INTERACTIVE_SELECTED_COLOR` preset, renders unlit/fully opaque, and is slightly larger than the selected Base/Overlay graph layer's node-size setting so it is not hidden by the underlying node.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `tests/test_graph_viewer_overlay.py`
- `docs/LOG.md`

3. Architecture decisions made
- Reused the same selected-node highlight actor path used by Single and Double View.
- Added small helpers to resolve highlight size from the active overlay interactive target and style the selected actor as an unlit overlay marker.

4. Assumptions
- Overlay Interactive selection should persist across ordinary overlay refreshes as long as the selected graph layer is still loaded.
- If the selected graph layer is removed or replaced with a non-GraphML layer, the existing clear-selection behavior remains correct.
- The selected marker should be visibly distinct even when graph node size is large, because same-size co-located point actors can be depth-tested or shaded into a dark color.

5. Limitations
- Manual desktop verification is still useful to confirm the highlight remains visible on dense or large graph layers.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`
- `/usr/bin/python3.12 -m py_compile skelhub/visualization/graph_viewer.py tests/test_graph_viewer_overlay.py`
- Dependency-stubbed `/usr/bin/python3.12` smoke script: passed overlay selected-node highlight color/size checks and overlay rebuild preserving/redrawing the selected highlight.
- Dependency-stubbed `/usr/bin/python3.12` smoke script: passed cyan highlight marker checks for larger-than-node point size, disabled lighting, full opacity, and unlit material properties.

7. Remaining risks or recommended next steps
- Run `python -m pytest tests/test_graph_viewer_overlay.py -q` and manually verify overlay Interactive selection in a desktop environment with dependencies installed.

## 2026-06-03 23:23 AEST

### Fix overlay refresh after NIfTI opacity and restore full NIfTI opacity

1. Summary of what changed
- Overlay refresh now always commits graph preview options before rebuilding overlay scenes, independent of the single-view `active_kind`.
- This prevents Base GraphML node size and edge thickness from falling back to defaults after changing Overlay NIfTI opacity.
- Scene actor opacity updates now use `_set_actor_opacity`, which also updates VTK opaque/translucent pass hints when supported.
- NIfTI actors moved back to opacity `1.0` now force opaque rendering immediately instead of waiting for a dropdown-triggered rebuild.
- Opacity values within `0.005` of the slider endpoints now snap to exact `0.0`/`1.0`, so a UI value displayed as `1` is not secretly rendered as a translucent value such as `0.998`.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `tests/test_graph_viewer_overlay.py`
- `docs/LOG.md`

3. Architecture decisions made
- Kept the overlay fix in the existing refresh pipeline instead of adding a separate graph-only overlay refresh path.
- Centralized scene actor opacity handling while leaving 2D UI overlay opacity unchanged.
- Rebuild NIfTI overlay actors when they cross the opaque/translucent boundary, because VTK can keep actors previously rendered with alpha in the translucent pass until the actor is reconstructed.

4. Assumptions
- Overlay scene rebuilds should always use the committed graph preview options for Base and Overlay graph layers.
- VTK render-pass hints are safe to set when the actor exposes `SetForceOpaque` and `SetForceTranslucent`.
- Slider values that visually round to endpoint labels should behave as exact endpoint values.

5. Limitations
- Manual desktop verification is still recommended to confirm VTK backend behavior with representative NIfTI opacity changes.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`
- `/usr/bin/python3.12 -m py_compile skelhub/visualization/graph_viewer.py tests/test_graph_viewer_overlay.py`
- Dependency-stubbed `/usr/bin/python3.12` smoke script: passed overlay refresh committing Base GraphML preview sizes while active file is NIfTI, and passed opacity `1.0` forcing a NIfTI actor opaque.
- Dependency-stubbed `/usr/bin/python3.12` smoke script: passed near-endpoint opacity snapping (`0.998` -> `1.0`), actor/pass invalidation, and NIfTI opaque-boundary overlay rebuild.
- `python -m pytest tests/test_graph_viewer_overlay.py -q` could not run because the local Python 3.13 pytest installation fails during import (`AttributeError: __spec__` in `py/_vendored_packages/apipkg`).
- `/usr/bin/python3.12 -m pytest tests/test_graph_viewer_overlay.py -q` could not run because pytest is not installed for Python 3.12.
- `python -m skelhub graphviz --help` could not run because `numpy` is not installed in the active Python environment.

7. Remaining risks or recommended next steps
- Run `python -m pytest tests/test_graph_viewer_overlay.py -q` and manually verify `skelhub graphviz` overlay mode in a desktop environment with dependencies installed.

## 2026-06-03 22:54 AEST

### Fix overlay-view graph sliders, opacity, target menus, and Interactive layout

1. Summary of what changed
- Overlay Node Size and Edge Thickness sliders now target the actual GraphML layer when only Base or only Overlay is a graph.
- Base Opacity now applies directly to Base GraphML actors as well as Base NIfTI actors.
- Overlay Appearance and Interactive `Target` controls now open dropdown menus with explicit `Base` and `Overlay` choices.
- Overlay Interactive controls now reserve layout space for the target row, coordinates, and node degree so X/Y/Z and Node dgr stay inside the Tools panel.
- Overlay interactive selection helpers now use the selected overlay graph layer instead of the single-view active file slot.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `tests/test_graph_viewer_overlay.py`
- `docs/LOG.md`

3. Architecture decisions made
- Added small overlay target helpers so appearance sliders and interactive selection share the same Base/Overlay resolution rules.
- Kept graph opacity tracking local to overlay `ViewState` actor lists instead of changing the public result or render API.
- Kept the viewer dependency set unchanged and continued using the existing PyVista/VTK overlay UI actor model.

4. Assumptions
- If exactly one overlay layer is GraphML, graph appearance sliders should control that layer without requiring a visible Target selector.
- If both overlay layers are GraphML, the Target dropdown should decide which layer the graph sliders or Interactive readout controls.
- Opacity changes should apply in place when actor references are available, with rebuild fallback kept for other cases.

5. Limitations
- Manual desktop verification is still recommended because custom VTK/PyVista overlay controls can be sensitive to window size and backend behavior.
- This patch does not change overlay camera framing or alignment-warning behavior.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`
- `/usr/bin/python3.12 -m py_compile skelhub/visualization/graph_viewer.py tests/test_graph_viewer_overlay.py`
- Dependency-stubbed `/usr/bin/python3.12` smoke script: passed overlay graph slider target selection, Base GraphML opacity update, Appearance Target menu selection, and Interactive Target menu selection.
- Full pytest could not be run in this local environment because Python 3.13 pytest fails during import and Python 3.12 does not have pytest installed.
- CLI smoke still cannot run in this local environment because `numpy` is not installed in the available interpreters.

7. Remaining risks or recommended next steps
- Run `python -m pytest tests/test_graph_viewer_overlay.py -q` and manually check `skelhub graphviz` overlay mode in a desktop-capable environment with project dependencies installed.

## 2026-06-03 22:15 AEST

### Fix overlay-view Base and Overlay file dropdown selection

1. Summary of what changed
- `skelhub graphviz` overlay-mode Base and Overlay dropdown buttons now store which layer they control, so the Base button opens the Base file menu instead of being treated like Overlay.
- Overlay dropdown assignment now accepts `None`, allowing the `Empty` row to clear either layer.
- The same loaded file can be assigned to both Base and Overlay because assignment no longer filters or swaps duplicate layer indices.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `tests/test_graph_viewer_overlay.py`
- `docs/LOG.md`

3. Architecture decisions made
- Kept the fix localized to the PyVista overlay UI event model and session assignment path.
- Reused existing `UIHitbox.index` metadata instead of adding a new UI state object.

4. Assumptions
- Overlay mode should allow any loaded visualization file or an empty layer for both Base and Overlay.
- Rendering the same file twice is acceptable and should use the existing base/overlay appearance styling.

5. Limitations
- This patch does not change overlay rendering order, alignment warnings, or per-layer appearance behavior.
- Manual desktop verification is still useful because the controls are custom VTK/PyVista overlay actors.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`
- `/usr/bin/python3.12 -m py_compile skelhub/visualization/graph_viewer.py tests/test_graph_viewer_overlay.py`
- Dependency-stubbed `/usr/bin/python3.12` dispatch smoke script: passed Base menu toggle, Empty layer clearing, and same-file Base/Overlay assignment checks.
- `python -m pytest tests/test_graph_viewer_overlay.py -q` could not run because the local Python 3.13 pytest installation fails during import (`AttributeError: __spec__` in `py/_vendored_packages/apipkg`).
- `/usr/bin/python3.12 -m pytest tests/test_graph_viewer_overlay.py -q` could not run because pytest is not installed for Python 3.12.
- `python -m skelhub graphviz --help` and `/usr/bin/python3.12 -m skelhub graphviz --help` could not run because `numpy` is not installed in those interpreters.

7. Remaining risks or recommended next steps
- Run `python -m pytest tests/test_graph_viewer_overlay.py -q` and a desktop `skelhub graphviz` session after installing the project dependencies in the active Python environment.

## 2026-06-03 11:30 AEST

### Fix overlay-view UI issues: file panel, slider overlap, header truncation

1. Summary of what changed
- **File panel hidden in overlay mode:** `render_file_panel` now exits early when `layout_mode in ("double", "overlay")` (was only `"double"`), removing the top-left dropdown.
- **Opacity slider overlap:** `_tools_panel_layout` shifts the `interactive_header` cursor down by `APPEARANCE_SLIDER_SPACING * 2` (168 px) in overlay mode, making room for the Base Opacity and Overlay Opacity sliders between the Appearance and Interactive sections.
- **Header filename-only truncation:** `_render_overlay_header` now only truncates the base and overlay filenames (keeping "Overlay View | Base: ... | Overlay: ..." prefix intact), matching the double-view header behavior.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

## 2026-06-03 11:00 AEST

### Fix three overlay-view limitations

1. Summary of what changed
- **Per-layer appearance (Limitation 1):** `ViewState` now has `base_options`, `overlay_options`, and per-layer preview values.  Slider commit path (`_commit_graph_preview_value`) and slider read path (`_appearance_slider_value`) branch on `view.overlay_target` in overlay mode, so the Target dropdown actually changes which layer's node/edge sizes are adjusted.  `_render_overlay_layers` uses `view.base_options`/`view.overlay_options` per layer.  `_add_overlay_graph` accepts an explicit `options` parameter.
- **In-place opacity (Limitation 2):** `ViewState` stores actor refs (`overlay_base_nifti_actor`, `overlay_overlay_nifti_actor`, `overlay_overlay_graph_actors`).  Opacity slider commits call `actor.GetProperty().SetOpacity()` directly without scene rebuild when a stored actor exists.
- **Overlay Interactive section (Limitation 3):** Added `interactive_overlay_target` to session.  In overlay mode, `render_interactive_controls` shows a Target dropdown between the Interactive toggle and Node-id row when both layers are GraphML.  `_selected_graph_data`, `_nearest_graph_node_index`, and `select_graph_node_at_display_position` all route through `interactive_overlay_target` to pick the correct layer's graph data.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

3. Remaining known limitations removed from LOG.

## 2026-06-03 10:00 AEST

### Overlay View layout mode (initial implementation)

1. Summary of what changed
- Added "Overlay View" as a third layout mode alongside Single and Double.
- **Data model**: `ViewState` gained `base_file_index`, `overlay_file_index`, `base_opacity` (default 0.8), `overlay_opacity` (default 0.5), and `overlay_target`.  Session gained `overlay_menu_open`, `assign_base_file`, `assign_overlay_file`, `base_file_for_view`, `overlay_file_for_view`, and `_validate_overlay_alignment`.
- **Layout dropdown**: "Overlay View" option added (index 2).  `set_layout_mode` handles overlay initialization.
- **View Layout section**: dynamic per mode — Single shows "View", Double shows "View A"/"View B", Overlay shows "Base"/"Overlay" file dropdowns.
- **Overlay rendering** (`_render_overlay_layers`): single viewport, both layers.  NIfTI base → blue blocks; GraphML overlay → red nodes + green edges; NIfTI overlay → orange blocks (#F27A4E, reduced opacity); dual GraphML → base default + overlay with blue edges (#4EC6F2) and orange nodes.
- **Header**: single "Overlay View | Base: ... | Overlay: ..." bar.
- **Appearance**: overlay mode adds Base Opacity / Overlay Opacity sliders (0.0–1.0) and a Target dropdown when both layers are GraphML.
- **Camera**: Sync Camera greyed out and no-op in overlay mode (single viewport, inherently synced).
- **Alignment**: NIfTI-NIfTI checks shape equality; GraphML-GraphML checks >= 97 % bounding-box overlap.  Warning dialog shown on mismatch.

2. New constants
- `OPACITY_RANGE`, `DEFAULT_BASE_OPACITY`, `DEFAULT_OVERLAY_OPACITY`, `OVERLAY_NIFTI_COLOR`, `OVERLAY_GRAPH_NODE_COLOR`, `OVERLAY_GRAPH_EDGE_COLOR`

3. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

4. Known limitations
- Node Size / Edge Thickness sliders in overlay mode are shared across both graph layers; per-layer appearance (driven by Target dropdown) is not yet wired into the slider commit path.
- Opacity changes trigger a full scene rebuild rather than an in-place property update.
- The Interactive section's overlay Target dropdown is defined in spec but not yet implemented.
- If both base and overlay files are loaded, the first-load assignment heuristic (base first, then overlay) may need explicit assignment via the dropdowns.

## 2026-06-02 19:30 AEST

### Header: pixel-based text truncation; immediate border update on click

1. Summary of what changed
- Header text truncation now uses viewport pixel width instead of a fixed char limit (`HEADER_MAX_CHARS` removed). Available width is `half_scene - 20` px; conservatively estimates 8 px per character and truncates only the filename portion, keeping the prefix intact.
- `set_active_view` now calls `plotter.render()` after updating headers, so the active-view border changes immediately on viewport click without waiting for the next VTK event-loop render.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

## 2026-06-02 19:20 AEST

### Add compact viewport header bars in double-view mode

1. Summary of what changed
- Added 5 %-height header bars above each viewport in double-view mode.
- Active view's header has a bright #F2F24E border; inactive uses the base #BBC3C7 color.
- Header shows "View A/B | [GraphML/NIfTI] filename" (truncated at 36 chars).
- Viewport scenes are offset vertically to make room for the headers (`header_bottom = 0.95`).
- Headers are rendered as 2D overlay actors and update on layout switches, active-view changes, window resizes, and file loads.

2. New constants
- `HEADER_HEIGHT_FRACTION = 0.05`, `HEADER_COLOR`, `HEADER_BORDER_COLOR`, `HEADER_BORDER_WIDTH = 2`, `HEADER_FONT_SIZE = 11`, `HEADER_MAX_CHARS = 36`

3. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

4. Architecture decisions
- `render_view_headers` is called from `add_graph_viewer_controls`, `render_active_graph`, `set_active_view`, and `_on_resize` — covering initial setup, layout switches, view switches, and resizes.

## 2026-06-02 19:00 AEST

### Content area fills panel height; scrollbar only when needed

1. Summary of what changed
- Removed the `TOOLS_PANEL_HEIGHT` (560 px) cap from `_tools_panel_visible_height`. The visible content area now fills the full panel height.
- Scrollbar only appears when the window is shorter than `TOOLS_PANEL_CONTENT_HEIGHT` (830 px) minus the top/bottom margins (24 px), i.e. below ~854 px window height.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

3. Architecture decisions
- At typical window heights (≥ 900 px) all tools-panel glyphs fit without scrolling. The scrollbar and scroll-handling logic remain in place for smaller windows.

## 2026-06-02 18:45 AEST

### Tools panel: flush full height, fully opaque

1. Summary of what changed
- The blue tools-panel background rect now spans the full window height (`y=0`, `height=window_height`) and is fully opaque (`opacity=1.0`, was `0.90`).
- This eliminates any black render-window background visible above or below the panel.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

3. Architecture decisions
- The content area and scrollbar geometry remain unchanged (`_tools_panel_geometry` still returns the content-based top/bottom for controls and scrollbar). Only the background overlay rect was extended to full height.

## 2026-06-02 18:30 AEST

### UI layout: fixed tools panel to 25 % window, removed Tools toggle button

1. Summary of what changed
- Scene right-edge is now a hard 75 % of the window (`_scene_area_fraction` returns `0.75`). The remaining 25 % is the always-visible tools panel.
- Removed the "Tools" toggle button and its hitbox entirely. The tools panel is now permanently visible.
- Replaced the fixed-pixel `TOOLS_PANEL_WIDTH` (336 px) with a dynamic `_tools_panel_width(plotter)` helper that returns 25 % of the window width.
- Panel starts at 75 % of window width (no gap to scene) and extends to the window right edge (no margin).
- Adjusted `_tools_panel_visible_height` to remove the button/gap deduction from the available height.
- Removed `tools_button_actors` from session; `tools_panel_visible` defaults to `True`.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

3. Architecture decisions
- Scene/viewport and tools panel now use a fixed 75/25 split rather than a pixel-based reservation. This eliminates the black "dead zone" background that appeared when the renderer viewport did not cover the full window.
- The tools panel is always visible, so all `tools_panel_visible` guards become no-ops (but are left in place for safety).

4. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`

5. Limitations
- At very narrow window widths (below ~500 px) the 25 % panel may be too narrow for all controls. The minimum panel width is not separately enforced beyond the scrollbar/padding logic inherited from the previous layout.

## 2026-06-02 18:15 AEST

### Fix orientation axes widget size mismatch in double-view mode (corrected)

1. Summary of what changed
- Changed `_axes_marker_viewport` to return renderer-relative coordinates instead of computing global window coordinates. VTK's `vtkOrientationMarkerWidget::SetViewport` interprets the viewport relative to the parent renderer, not the full window.
- Removed the unused `scene_left` and `scene_right` parameters; the function now only takes `scale_x`.
- In `apply_view_layout`, pass `scale_x=2.0` for double-view mode so the width span doubles (2%-38% of renderer instead of 2%-20%), compensating for the halved renderer width.
- Single-view mode uses `scale_x=1.0` (default), producing the intended 2%-20% renderer-relative viewport.

2. Root cause
- The previous implementation incorrectly treated `SetViewport` as accepting global window coordinates and scaled the viewport by `scene_width`, producing values that were disproportionately small in double-view mode. The single-view case happened to look acceptable because the renderer starts at (0,0).

3. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

4. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`

## 2026-06-02 18:00 AEST

### ~~Fix orientation axes widget size mismatch in double-view mode~~ (superseded by 18:15 entry)

## 2026-06-02 17:50 AEST

### Suppress igraph duplicate 'id' vertex attribute warning on GraphML load

1. Summary of what changed
- Wrapped `ig.Graph.Read_GraphML` in `load_graph_visualization_data` with a targeted `warnings.catch_warnings` filter that ignores the RuntimeWarning "Could not add vertex ids, there is already an 'id' vertex attribute".
- Added `import warnings` to the module imports.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

3. Architecture decisions
- Chose targeted warning suppression over changing the igraph read/write parameter mapping because the warning originates from igraph's internal GraphML roundtrip behavior (the writer stores `name` as both XML `id` and `<data key="name">`, and the reader collides when trying to map XML `id` → vertex `id` that already exists).
- The warning is harmless — graph rendering and node-id extraction both work correctly regardless.

4. Assumptions
- The warning is purely cosmetic and does not affect data integrity.
- Future igraph versions may change the default `index` parameter behavior; the targeted suppression is version-agnostic.

5. Limitations
- Only suppresses this specific duplicate-attribute warning; other igraph warnings during GraphML I/O will still surface.

6. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`
- `python -m skelhub graphviz --help`

## 2026-06-02 17:20 AEST

### Tools panel slider containment and dropdown layering

1. Summary of what changed
- Replaced the PyVista Appearance slider widgets with Tools-panel overlay sliders for `Node Size` and `Edge Thickness`.
- Kept slider tracks, knobs, labels, values, and hitboxes constrained to the side-panel inner width.
- Added click-and-drag handling for the overlay sliders while preserving the existing graph appearance update path.
- Rendered open dropdown menus as the final Tools-panel overlay pass so they display above buttons, sliders, and scrollbar actors.
- Changed dropdown menu rows to draw full rectangular backgrounds matching their hitbox size.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

3. Assumptions and tradeoffs
- Overlay sliders intentionally replace VTK slider widgets in the side panel to avoid panel clipping and layer conflicts.
- Disabled Appearance rows for empty or NIfTI active views remain visible but do not expose slider hitboxes.

4. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`
- `python -m skelhub graphviz --help`
- Off-screen UI smoke check for slider containment, slider click update, dropdown row hitbox sizing, and disabled NIfTI appearance hitboxes.
- `git diff --check`

5. Limitations and remaining risks
- Desktop visual review is still needed to confirm dropdown stacking and slider drag feel on the target display backend.

## 2026-06-02 17:00 AEST

### Multi-view viewer follow-up fixes

1. Summary of what changed
- Fixed the Tools-panel crash caused by `selected_node_position(...)` referencing an undefined `view` variable.
- Increased right-side panel and overlay text sizes and button height for readability.
- Hid top-left file dropdowns in `Double View`; active file assignment is now only through the right-side `View A` / `View B` controls.
- Kept the `Apperance` section visible for empty or NIfTI active views by rendering disabled grey slider rows.
- Set both viewport axes markers to the same local lower-left viewport placement.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/visualization.md`
- `docs/LOG.md`

3. Architecture decisions made
- Preserved right-panel file assignment as the only Double View file-switching path.
- Kept the existing PyVista axes marker approach, with explicit marker viewport placement.

4. Assumptions and tradeoffs
- Treated "coordinate legend" as the PyVista axes marker shown in the scene viewport.
- Larger text may reduce the number of rows visible before scrolling, but improves readability.

5. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`
- `python -m skelhub graphviz --help`
- Off-screen PyVista smoke check opening the Tools panel after switching to `Double View`.
- `git diff --check`

6. Limitations and remaining risks
- Desktop visual review is still needed to verify axes marker placement and font sizing on the target display backend.

## 2026-06-02 16:22 AEST

### Graph viewer multi-view layout mode

1. Summary of what changed
- Added `Single View` / `Double View` layout state with per-viewport file assignment, appearance settings, selected-node state, scene actors, and camera interaction state.
- Added a `View Layout` Tools-panel section with `Layout`, `View A`, and `View B` dropdown controls.
- Added double-view rendering using two PyVista scene renderers plus a full-window 2D overlay renderer for file panels and Tools controls.
- Kept single-view as the default and preserved the existing one-view file workflow.
- Changed NIfTI appearance behavior so the `Apperance` section remains visible with disabled grey slider rows.
- Consumed mouse-wheel events inside the Tools panel so panel scrolling does not zoom a viewport.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/visualization.md`
- `docs/LOG.md`

3. Architecture decisions made
- Kept one global loaded-file list and moved active file, scene actors, selection, interactive mode, and appearance values into per-view state.
- In double-view mode, `Close` clears only the active viewport assignment and does not unload the file globally.
- Used a dedicated overlay renderer for 2D UI actors so top-left file panels and side-panel controls do not depend on the active scene renderer.

4. Assumptions and tradeoffs
- `View A` and `View B` may select the same loaded file.
- `View B` starts empty when switching from single view to double view.
- `Double View` forces `Sync Camera` on, but users can still toggle sync afterward.

5. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`
- `python -m skelhub graphviz --help`
- Off-screen PyVista smoke check loading `test_data/simple_graph/sample.graphml`, switching to double view, assigning the graph to `View B`, rendering both views, and closing the plotter.
- Focused state check confirming double-view `Close` clears only the active viewport and per-view appearance values do not leak.
- `git diff --check`

6. Limitations and remaining risks
- Desktop visual review is still needed to confirm overlay placement, dropdown interaction, and camera synchronization feel right on the target VTK/PyVista backend.

## 2026-06-02 15:00 AEST

### Tools panel scroll containment and smoother dragging

1. Summary of what changed
- Changed Tools-panel row visibility from partial intersection to full containment, with a small viewport padding, so text, boxes, buttons, and slider reserved areas are not drawn outside the panel while scrolling.
- Suppressed live slider-widget reconstruction during scrollbar dragging and restored sliders once the drag is released.
- Matched the panel background rectangle height to the visible panel height instead of the fixed content height.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

3. Architecture decisions made
- Kept the existing PyVista/VTK overlay implementation and scroll state; the fix is localized to visibility checks and drag-time rendering.
- Used the existing final render call after each scroll update, but skipped expensive VTK slider recreation during continuous thumb movement.

4. Assumptions and tradeoffs
- This should smooth scrollbar dragging most noticeably; mouse-wheel scrolling may still rebuild visible sliders on each wheel step.
- Fully contained rows disappear at panel edges instead of being partially clipped, because these overlay actors are not natively clipped to the panel rectangle.

5. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`

6. Limitations and remaining risks
- Desktop visual review is still needed to confirm perceived blink reduction on the target VTK/PyVista backend.

## 2026-06-02 14:36 AEST

### Tools panel slider spacing and section headers

1. Summary of what changed
- Added a reserved vertical buffer zone around the `Node Size` and `Edge Thickness` slider widgets so later controls are positioned away from the slider title and track area.
- Increased the Tools-panel scrollable content height to cover the larger buffered layout.
- Changed section headers to centered bold text with independent separator lines on both sides.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

3. Architecture decisions made
- Kept the existing PyVista slider widgets and button hitboxes; only the shared overlay layout and section header drawing changed.
- Made slider spacing explicit with named constants so future UI edits can preserve the reserved area.

4. Assumptions and tradeoffs
- Treated the requested "session titles" as the Tools-panel section titles.
- Kept the requested visible section spelling `Apperance`.

5. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`

6. Limitations and remaining risks
- Desktop visual review is still recommended because PyVista slider text extents vary by backend and display scaling.

## 2026-06-02 14:15 AEST

### Grouped graph viewer Tools panel

1. Summary of what changed
- Grouped the right-side `Tools` panel controls into `Session`, `Camera`, `Apperance`, and `Interactive` sections.
- Moved `Sync Camera`, `Reset View`, and `Fit Preview` into the Camera section while preserving their existing actions.
- Kept the interactive toggle text as `Interactive` and reordered the interactive fields to show `Node id` before `X`, `Y`, `Z`, and `Node dgr`.

2. Files modified
- `skelhub/visualization/graph_viewer.py`
- `docs/LOG.md`

3. Architecture decisions made
- Reused the existing PyVista/VTK overlay actors, hitboxes, callbacks, and slider widgets instead of replacing the panel implementation.
- Added a shared section-layout helper so related controls are positioned from one grouped layout map.

4. Assumptions and tradeoffs
- Used the requested visible section spelling `Apperance`.
- Kept GraphML appearance sliders hidden for active NIfTI files, matching the previous behavior.

5. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py`
- `python -m skelhub graphviz --help`

6. Limitations and remaining risks
- Desktop visual review is still recommended to confirm the section spacing feels right with real PyVista text and slider rendering.
- The help command emitted the existing Matplotlib writable-cache warning and used a temporary `/tmp` cache directory.

## 2026-05-27 AEST

### Laplacian verbose progress reporting

1. Summary of what changed
- Added verbose Laplacian pipeline reporting with current-stage labels, a stage-completion progress bar, elapsed time, and estimated remaining-time countdown.
- Added live graph-contraction iteration reports including node count, cycle area, and convergence target.
- Kept reporting behind the existing `--verbose`/`log` route so quiet execution and shared backend contracts remain unchanged.

2. Tests run
- `python -m py_compile skelhub/algorithms/laplacian/progress.py skelhub/algorithms/laplacian/backend.py skelhub/algorithms/laplacian/skeleton.py skelhub/algorithms/laplacian/contract_graph.py tests/test_laplacian_progress.py`
- `python -m pytest tests/test_laplacian_progress.py -q` (`2 passed`)
- `python -m pytest -q` (`15 passed`)
- `python -m skelhub run --algorithm laplacian --input tests/fixtures/straight_tube.nii.gz --output /tmp/skelhub_laplacian_progress.nii.gz --verbose`
- `git diff --check`

## 2026-05-27 AEST

### World-coordinate NIfTI rendering and synchronized camera

1. Summary of what changed
- Rendered NIfTI foreground blocks in physical/world coordinates from the image affine, so compatible NIfTI and GraphML `X/Y/Z` data occupy the same displayed frame.
- Changed the Tools-panel `Sync Camera` toggle, enabled by default, to preserve the exact displayed-world camera when switching among GraphML and NIfTI files.
- Kept source voxel indices in NIfTI visualization data while displaying and editing NIfTI cursor `X/Y/Z` values in world coordinates.

2. Architecture decisions made
- Applied the full affine to NIfTI rendering: voxel centres use affine-transformed locations and the shared glyph cube uses the affine linear component to preserve scale, rotation, permutation, and flip.
- Replaced the pending relative-bounds camera pose with the existing complete `CameraState`, including projection and parallel-scale properties.
- Used affine-transformed voxel-cell corner bounds for NIfTI cursor initialization and empty-volume handling, while retaining per-file cursor positions.

3. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py tests/test_graph_camera_travel.py tests/test_graph_camera_sync.py`
- `python -m pytest -q` (`13 passed`)
- `python -m skelhub graphviz --help`
- `git diff --check`
- Off-screen PyVista smoke check on the ex-vivo NIfTI/GraphML pair, confirming affine-transformed graph `voxel_pos` values match stored `X/Y/Z` and synchronized file switching retains the same world camera.

4. Limitations and remaining risks
- Synchronized views assume that loaded GraphML `X/Y/Z` coordinates and NIfTI affines describe the same world frame; unregistered files may require disabling `Sync Camera`.
- Desktop review remains needed to confirm the expanded Tools-panel layout, physical overlay appearance, and camera navigation feel on representative scenes.

## 2026-05-27 AEST

### Unlimited GraphML camera travel

1. Summary of what changed
- Replaced focal-point-limited wheel zoom for active GraphML scenes with forward/backward travel along the current camera direction.
- Kept standard PyVista wheel navigation unchanged for NIfTI inputs and empty viewer sessions.
- Preserved stored initial camera state so `Reset View` restores the original GraphML framing after travelling through the scene.

2. Architecture decisions made
- Implemented the behavior in the existing cancellable VTK observer path, translating camera position and focal point together by `2.5%` of their distance for each wheel event.
- Kept the behavior private to the interactive visualization module, without changing CLI arguments or public APIs.

3. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py`
- `python -m pytest tests/test_graph_camera_travel.py -q`
- `python -m skelhub graphviz --help`
- `git diff --check`
- Off-screen PyVista GraphML smoke check covering custom forward camera travel and reset-to-initial view.

4. Remaining risks
- The exact mouse-wheel travel feel should still be checked in a desktop viewer on a representative large GraphML graph.

## 2026-05-27 AEST

### Movable Tools-panel cursor

1. Summary of what changed
- Added a Tools-panel `Enable Cursor` toggle and editable `X`, `Y`, and `Z` coordinate rows for a per-file viewport crosshair, including restored enable state when returning to a loaded file.
- Added camera-plane left-drag movement and retained the enabled crosshair when the Tools panel is hidden.
- Preserved existing scene coordinate behavior: GraphML coordinates remain rendered `X/Y/Z`, while NIfTI cursor values remain voxel-index coordinates.

2. Architecture decisions made
- Implemented the crosshair and numeric fields through the existing PyVista/VTK overlay and observer approach, without adding dependencies or changing public viewer/CLI interfaces.
- Kept cursor positions per loaded file rather than attempting synchronization between GraphML world coordinates and NIfTI voxel-index coordinates.

3. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py skelhub/api.py`
- `python -m skelhub graphviz --help`
- `git diff --check`
- Off-screen PyVista cursor interaction smoke check covering Tools-panel rows, activation initialization, hidden-panel persistence, numeric commit/cancel/invalid entry, camera-plane dragging, per-file GraphML/NIfTI cursor restoration, no-file activation blocking, and continued NIfTI appearance-control hiding.

## 2026-05-27 AEST

### Instanced NIfTI block rendering

1. Summary of what changed
- Optimized interactive NIfTI display in `skelhub graphviz` by using one VTK unit-cube glyph source instanced at each foreground voxel.
- Kept NIfTI validation, `[NIfTI]` status labeling, import warning behavior, unit-block appearance, and the exported `build_nifti_meshes(...)` helper unchanged.

2. Architecture decisions made
- Applied instanced rendering to all non-empty interactive NIfTI scenes because it preserves the existing visible block contract without needing an arbitrary dense-volume cutoff.
- Kept the optimization private to scene actor construction, parallel to the existing optimized GraphML scene paths.

3. Performance basis and tests run
- Representative input `test_outputs/exvivo/Skel_S64520_m0_SLA_colliculi_cropped_smaller_vessels_binary_th_0.1_masked_cleaned_cc_10.nii.gz` contains `62,478` foreground voxels.
- Baseline expanded block mesh produced `499,824` points and `374,868` cells using approximately `32.42 MB` of mesh storage; the instanced point-cloud plus shared-cube setup used approximately `2.43 MB` of input geometry storage in the inspection run.
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py skelhub/api.py`
- `python -m skelhub graphviz --help`
- Focused behavior smoke check covering unchanged NIfTI loading/foreground extraction, empty-volume handling, instanced mapper source/input geometry, block colors/edge visibility, compatibility of `build_nifti_meshes(...)`, and active-scene actor creation.
- Off-screen representative-volume render smoke check; in this run expanded mesh setup took approximately `0.0562 s`, while instanced actor setup took approximately `0.0038 s`.

## 2026-05-27 AEST

### Graph viewer Tools side panel

1. Summary of what changed
- Moved the `skelhub graphviz` command controls and GraphML appearance sliders into a pure-PyVista right-side `Tools` panel that starts hidden and toggles from a persistent top-right button.
- Confirmed the `Tools` toggle is rendered at viewer initialization and remains visible when its panel is opened or closed.
- Repositioned right-side controls on VTK `ConfigureEvent` so a desktop startup resize or later window resize cannot leave the `Tools` button beyond the visible right edge.
- Initializes/maps the PyVista desktop window in non-blocking mode, redraws the right-side controls using its actual startup dimensions, then starts normal interaction; this covers backends that do not emit `ConfigureEvent` during initial creation.
- Kept the top-left loaded-file dropdown unchanged and preserved the existing `Import`, `Close`, previous/next, `Refresh`, and `Reset View` behaviors.
- Added Node Size and Edge Thickness `-` / `+` controls that adjust pending values in `0.1` increments while preserving refresh-to-apply rendering.

2. Architecture decisions made
- Kept the viewer dependency-free beyond the existing PyVista/VTK stack by rendering the side panel as in-canvas overlay actors and hitboxes.
- Continued to hide GraphML appearance controls for active NIfTI files while leaving panel session commands available.
- Recreated only slider widgets after step-button clicks so their visible values track pending settings without rebuilding graph geometry.

3. Tests run
- `python -m py_compile skelhub/visualization/graph_viewer.py skelhub/visualization/__init__.py skelhub/cli/main.py skelhub/api.py`
- `python -m skelhub graphviz --help`
- Focused fake-plotter interaction smoke check covering Tools visibility toggling, unchanged file hitboxes, panel actions, slider step/clamping behavior, deferred appearance application, and NIfTI appearance-control hiding.
- Focused resize-observer smoke check confirming a smaller post-startup render-window size redraws the persistent `Tools` toggle inside the new right edge.
- Focused desktop-initialization smoke check confirming the first non-blocking show establishes a smaller native window size before `Tools` is redrawn and normal interaction begins.
- Off-screen PyVista smoke check loading `test_data/simple_graph/sample.graphml`, opening the Tools panel, stepping Node Size, refreshing the graph, rendering, and closing the plotter.

## 2026-05-26 AEST

### Dual-space Voreen-style feature extraction

1. Summary of what changed
- Added `skelhub.postprocessing.feature` for branch and node feature export from binary vessel foreground, binary skeleton, and compatible GraphML.
- Added `skelhub feature` plus the public `extract_features_from_paths(...)` API.
- Added edge and node CSV output. Base edge measurements are voxel-space values; image-space length/radius columns are suffixed with the NIfTI header spatial unit. Node rows include voxel-space position and GraphML incidence degree.

2. Architecture decisions made
- Accepted GraphML from `skelhub graphgen` and Laplacian `--graph_output`; stored GraphML `centerline_voxels` are authoritative branch paths.
- Kept node CSV positions in voxel coordinates and exported each node's graph incidence degree.
- Calculated image-space distance and radius by axis-wise foreground-header voxel sizes, rather than the full affine. This keeps measurements tied to image spacing and reports units as `_mm`, `_um`, `_m`, or `_unknown`.
- Ran foreground-to-edge assignment independently in voxel and image spaces so anisotropic spacing can change branch assignment and radius values.
- Implemented Voreen-style nearest-edge assignment, connected-component anchoring, 6-neighbor filling of unresolved foreground, surface-distance radius samples, and per-edge local-radius means.

3. Assumptions
- Base edge columns `length`, `minRadius`, `avgRadius`, `maxRadius`, and `curveness` are intentionally voxel-space values.
- `node1_degree` and `node2_degree` identify the degree of their named endpoint IDs, rather than Voreen's sorted endpoint-degree export.
- Topology-only edges with no centerline samples retain length and curveness but write `NaN` radius values.
- GraphML paths may differ from the supplied skeleton for Laplacian cleaned graph output; this is logged as a warning and does not block extraction.

4. Tests run
- `python -m py_compile skelhub/postprocessing/feature/*.py skelhub/postprocessing/__init__.py skelhub/api.py skelhub/__init__.py skelhub/cli/main.py tests/test_feature.py`
- `python -m pytest tests/test_feature.py -q`
- `python -m skelhub feature --help`

## 2026-05-23 AEST

### Documentation readability refresh

1. Summary of what changed
- Reworked `README.md` into a shorter project entry point with overview, installation, four CLI doc links, repository structure, and structured-output pointer.
- Moved Python API guidance into `docs/API.md`.
- Added `docs/StructuredOutput.md` for the current framework result containers and output files.
- Added `docs/visualization.md` for `skelhub graphviz` usage, input requirements, and HPC/conda notes.
- Reorganized `docs/algorithms.md` into distinct backend sections, with `laplacian` first as the current priority backend.

2. Architecture decisions made
- Kept README focused on orientation and navigation rather than detailed command examples.
- Kept detailed CLI and API behavior in topic-specific docs.
- Left the structured output contract marked as review pending.

3. Assumptions
- The README `CLI Usage` section should contain four links: Algorithms, Evaluation, Visualization, and Python API.
- `docs/StructuredOutput.md` is referenced from README outside the CLI Usage section.

4. Tests run
- Documentation-only change; no runtime tests required.

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
