# Algorithms

## Flux Backend

The flux backend is integrated under `skelhub.algorithms.flux`. It implements a Python-native flux-driven medial curve extraction flow for already-binary 3D volumes, following the VMTK/EvoLib medial-curve behavior without copying VMTK source code or including any surface-to-binary conversion.

Framework-facing usage:

```bash
skelhub run --algorithm flux --input input.nii.gz --output out.nii.gz
skelhub run --algorithm flux --input input.nii.gz --output out.nii.gz \
    --flux-threshold 0.0 \
    --flux-sigma 0.5 \
    --flux-sigma-unit physical \
    --verbose
```

Backend-specific parameters:

- `--flux-threshold FLOAT` controls the average-outward-flux endpoint preservation threshold. Default: `0.0`.
- `--flux-sigma FLOAT` controls Gaussian smoothing of the signed-distance image before gradient computation. Default: `0.5`.
- `--flux-sigma-unit {physical,voxels}` controls whether sigma is interpreted in NIfTI physical units or direct voxel units. Default: `physical`.

Implementation notes:

- Input must be exactly binary `{0, 1}`; non-binary volumes are rejected rather than thresholded.
- The backend computes a signed Euclidean distance with foreground at `<= 0` and background at `> 0`, computes 26-neighborhood average outward flux from the smoothed signed-distance gradient, and performs topology-preserving priority thinning.
- Topology checks use 26-connected foreground simplicity and 18-neighborhood background simplicity with 6-connectivity.
- The backend returns a same-shape binary `uint8` skeleton volume and does not attach a graph result.
- Provenance: the local VMTK repository is BSD-style licensed. This backend documents the VMTK/EvoLib and Bouix-Siddiqi-Tannenbaum reference path but is implemented from scratch in Python; no VMTK source code is copied.

## Palagyi-Kuba Backend

The Palagyi-Kuba backend is integrated under `skelhub.algorithms.palagyi_kuba`. It implements a Python-native 12-subiteration 3D thinning flow from the local Palagyi and Kuba reference notes and template figures.

Framework-facing usage:

```bash
skelhub run --algorithm palagyi_kuba --input input.nii.gz --output out.nii.gz
skelhub run --algorithm palagyi_kuba --input input.nii.gz --output out.nii.gz \
    --pk-mode surface \
    --pk-binarize-threshold 0.5 \
    --pk-max-cycles 20 \
    --verbose
```

Backend-specific parameters:

- `--pk-mode {curve,surface}` selects curve endpoint preservation with the 14 curve templates, or surface endpoint preservation with the 6 surface templates.
- `--pk-binarize-threshold FLOAT` thresholds non-binary input volumes before thinning. Default: `0.5`.
- `--pk-max-cycles INT` optionally caps full 12-direction thinning cycles.

Implementation notes:

- The direction convention is axis0 = U/D, axis1 = N/S, axis2 = W/E; U/N/W are negative axis directions and D/S/E are positive.
- The subiteration order is `US, NE, DW, SE, UW, DN, SW, UN, DE, NW, UE, DS`.
- Template tables are encoded locally from `PK_templates_figure.png` and `PK_surface_templates_figure.png`, then transformed into each subiteration direction.
- The backend returns a same-shape binary `uint8` skeleton volume and does not attach a graph result.
- Metadata records template source, axis mapping, per-direction deletion counts, cycle count, input/output foreground counts, and whether `--pk-max-cycles` stopped the run.

## L1 Skeleton Backend

The L1 skeleton backend is integrated under `skelhub.algorithms.l1_skeleton`. It is a Python-native implementation of the v2 L1-medial skeleton flow described in the local L1-Skeleton roadmap and informed by the original C++/Qt point-cloud repository.

Framework-facing usage:

```bash
skelhub run --algorithm l1_skeleton --input input.nii.gz --output out.nii.gz
skelhub run --algorithm l1_skeleton --input input.nii.gz --output out.nii.gz \
    --l1-sample-count 512 \
    --l1-initial-radius 2.0 \
    --l1-max-radius 8.0 \
    --l1-max-iterations 80 \
    --verbose
```

Backend-specific parameters:

- `--l1-sample-count` limits the number of moving samples seeded from foreground voxels.
- `--l1-initial-radius`, `--l1-radius-growth`, and `--l1-max-radius` control the local neighborhood schedule.
- `--l1-max-iterations` and `--l1-stop-error` control contraction convergence.
- `--l1-repulsion-mu` and `--l1-repulsion-mu-min` control conditional repulsion.
- `--l1-random-seed` makes foreground point sampling deterministic.
- `--l1-output-mode {branches,points}` selects the default v2 branch-curve rasterization or the previous contracted-point rasterization.
- `--l1-use-density-weighting` / `--no-l1-use-density-weighting` controls inverse local-density weighting during attraction.
- `--l1-use-recentering` / `--no-l1-use-recentering` controls branch-local ellipse re-centering before branch rasterization.

Implementation notes:

- Input NIfTI foreground is `data > 0`; output is same-shape binary `uint8`.
- Foreground voxels are converted to point coordinates using voxel spacing when available, contracted with KDTree neighborhoods, and processed through the v2 branch flow by default.
- V2 applies optional inverse local-density weighting, searches high-confidence contracted samples into branch curves with virtual endpoint handling, merges nearby branch endpoints, segments/smooths final curves, and optionally re-centers branch nodes by fitting local cross-section ellipses described in the local `ALGORITHM.md` note.
- The default skeleton output rasterizes final branch curves. `--l1-output-mode points` keeps the earlier contracted-sample rasterization path available for direct comparison.
- The current backend does not emit GraphML or attach a `GraphResult`; the previous sparse graph builder was removed because it was not part of the original L1-Skeleton code path.
- The backend metadata records output mode, branch counts, branch points, density weighting, re-centering attempts/applications, segmentation status, and convergence statistics.
- The original L1-Skeleton C++ repository does not contain a clear license file, and its README contains only placeholder license text. The backend therefore does not copy original source code; it uses the report/repo for traceability only.

## Laplacian Backend

The Laplacian backend is integrated under `skelhub.algorithms.laplacian`. It ports the required VascGraph `Skeletonize` path into SkelHub and updates the graph code for NetworkX 3.x compatibility.

Framework-facing usage:

```bash
skelhub run --algorithm laplacian --input input.nii.gz --output out.nii.gz
skelhub run --algorithm laplacian --input input.nii.gz --output out.nii.gz \
    --graph_output out.graphml \
    --graph_original original.graphml \
    --speed_param 0.05 \
    --dist_param 0.5 \
    --med_param 0.5 \
    --degree_threshold 5.0 \
    --sampling 1 \
    --clustering_r 1 \
    --stop_param 0.001 \
    --n_free_iteration 0 \
    --area_param 50.0 \
    --poly_param 10 \
    --verbose
```

Backend-specific parameters:

- `--graph_output PATH` writes the cleaned graph after `post_node_cleaning()` as GraphML with world-coordinate `X`, `Y`, `Z` fields and voxel-position metadata.
- `--graph_original PATH` writes the refined graph before `post_node_cleaning()` as GraphML with the same coordinate convention.
- `--speed_param`, `--dist_param`, `--med_param`, `--degree_threshold`, `--sampling`, `--clustering_r`, `--stop_param`, `--n_free_iteration`, `--area_param`, and `--poly_param` expose the VascGraph demo skeleton settings with the same defaults used in `demo_skeleton.py`.

Implementation notes:

- This backend is graph-native internally: it builds a dense foreground graph, contracts it toward vessel centerlines, refines small polygon artifacts, and removes degree-2 nodes from the cleaned graph.
- SkelHub still receives a standard binary skeleton NIfTI output. The cleaned graph is rasterized into the source volume shape by drawing every graph edge as a 26-connected voxel path.
- `--graph_output` is written from the cleaned graph rather than from the rasterized skeleton. `--graph_original` is available when the refined pre-cleaning graph is needed for inspection.
- Only the required VascGraph skeleton path is ported; unrelated VascGraph I/O, visualization, directed-graph, Pajek/SWC, and patch-stitching features are not included in this backend.

## Lee94 Backend

The Lee94 backend is integrated under `skelhub.algorithms.lee94`. The original implementation(skimage) already does zero padding to the input volume, so the SkelHub adapter does not add additional padding. 

Framework-facing usage:

```bash
skelhub run --algorithm lee94 --input input.nii.gz --output out.nii.gz
skelhub run --algorithm lee94 --input input.nii.gz --output out.nii.gz \
    --binarize-threshold 0.5 \
    --verbose
```

Backend-specific parameter:

- `--binarize-threshold FLOAT` controls the threshold used to convert normalized input intensities into a binary foreground mask before skeletonization. The default is `0.5`.

Implementation notes:

- This backend does not reimplement Lee et al. 1994 thinning manually.
- It wraps `skimage.morphology.skeletonize(..., method="lee")` inside a SkelHub backend adapter.
- The adapter validates that the loaded input is 3D, thresholds it to a binary mask, runs the wrapped scikit-image implementation, and returns the framework-standard `SkeletonResult`.
- Lee94-specific behavior is isolated under `skelhub/algorithms/lee94/` and does not alter the MCP backend mathematics.

## MCP Backend

The original repository content is now integrated as the first SkelHub backend under `skelhub.algorithms.mcp`.

Framework-facing usage:

```bash
# Run with default parameters:
skelhub run --algorithm mcp --input input.nii.gz --output out.nii.gz
# Run with custom parameters:
skelhub run --algorithm mcp --input input.nii.gz --output out.nii.gz \
    --root-method max_fdt \
    --threshold-scale 1.0 \
    --dilation-factor 2.0 \
    --max-iterations 200 \
    --min-object-size 50 \
    --label-objects \
    --verbose
```

Backend-specific parameters:

- `--root-method {max_fdt,topmost}` controls how the root voxel is chosen for each disconnected object.
  Use `max_fdt` (default) to start from the deepest interior voxel. Use `topmost` to prefer a root near the top of the object, which can be useful for airway-like data with a known superior-to-inferior orientation.
  Default is `max_fdt`.
- `--threshold-scale FLOAT` multiplies the branch-significance acceptance threshold. The default is `1.0`.
  Increase it to make branch acceptance more conservative and reduce weak side branches. Decrease it slightly to keep more marginal branches. The value must be positive.
- `--dilation-factor FLOAT` scales the FDT value used when generating the marked-mask dilation around the root and accepted branches. The default is `2.0`.
  Leaving it unset preserves the current behavior, where the dilation radius is `2 * FDT(p)` at each branch voxel. The value must be positive.
- `--max-iterations INT` sets the maximum number of outer skeleton-growth iterations per object. Default: `200`.
  This is a safety cap for complex or pathological inputs. If the cap is reached, the program stops growing that object safely and reports it in verbose mode.
- `--min-object-size INT` ignores connected components smaller than the given voxel count. Default: `50`.
  This is useful for filtering out isolated specks or segmentation noise before skeletonization begins.
- `--label-objects` writes each object's skeleton voxels using its connected-component label instead of writing all skeleton voxels as `1`.
  This is useful when the input volume contains multiple disconnected trees and you want to keep them distinguishable in the output. Default behavior is to write all skeleton voxels as `1`, without this flag.
- `--verbose` prints progress and runtime reporting during processing.

Implementation notes:

- The algorithm implements NIfTI-based curve skeletonization inspired by Jin et al. for tree-like 3D objects.
- The current code path includes multi-object decomposition, FDT and LSF computation, geodesic distance, minimum-cost path extraction, local scale-adaptive dilation, and Milestone 7 reporting behavior.
- Verbose MCP execution reports object counts, per-object iterations, branches added per iteration, branch counts, and runtime summaries.
- The MCP mathematics and intended growth-loop behavior are preserved from the pre-refactor code path.
- MCP-specific orchestration remains isolated in `skelhub/algorithms/mcp/multi_object.py`.
- The framework core does not depend on MCP internals; it only consumes the standardized result object returned by the backend adapter.
