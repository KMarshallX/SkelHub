# Algorithms

SkelHub backends all run through the same command shape:

```bash
skelhub run --algorithm <name> --input input.nii.gz --output out.nii.gz
```

Each backend stays isolated under `skelhub.algorithms.<name>`.

## Contents

- [Laplacian Backend](#laplacian-backend)
- [MCP Backend](#mcp-backend)
- [Lee94 Backend](#lee94-backend)
- [L1 Skeleton Backend](#l1-skeleton-backend)
- [Palagyi-Kuba Backend](#palagyi-kuba-backend)
- [Flux Backend](#flux-backend)

## Laplacian Backend

**Current priority backend.** Use `laplacian` when you want the graph-contraction path adapted from VascGraph, with optional GraphML export.

### CLI

```bash
skelhub run --algorithm laplacian --input input.nii.gz --output out.nii.gz
```

With graph outputs and tuned parameters:

```bash
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

### Parameters

- `--graph_output PATH`: write the cleaned graph after `post_node_cleaning()`.
- `--graph_original PATH`: write the refined graph before `post_node_cleaning()`.
- `--speed_param`, `--dist_param`, `--med_param`, `--degree_threshold`, `--sampling`, `--clustering_r`, `--stop_param`, `--n_free_iteration`, `--area_param`, `--poly_param`: expose the VascGraph demo skeleton settings.
- `--verbose`: show connected-component processing progress, elapsed time, and estimated remaining time.

### Notes and Limits

- The backend is graph-native internally.
- SkelHub still returns a standard binary skeleton NIfTI.
- Foreground input is decomposed into 26-connected components before Laplacian contraction; each component is processed independently and merged into the final outputs.
- The standard NIfTI output is rasterized from `graph_original`.
- Degree-2 chains use quadratic Bezier interpolation before 26-connected voxel path filling.
- If one component reaches the Laplacian contraction iteration cap, SkelHub warns and continues with that component's latest contracted graph.
- `--graph_output` writes one aggregate cleaned graph; `--graph_original` writes one aggregate refined graph used for rasterization.
- Only the required VascGraph skeleton path is ported. Unrelated VascGraph I/O, visualization, directed graph, Pajek/SWC, and patch-stitching features are not included.

### Citation

```text
R. Damseh, P. Delafontaine-Martel, P. Pouliot, F. Cheriet, and F. Lesage, "Laplacian Flow Dynamics on Geometric Graphs for Anatomical Modeling of Cerebrovascular Networks," *IEEE Transactions on Medical Imaging*, vol. 40, no. 1, pp. 381-394, Jan. 2021, doi: 10.1109/TMI.2020.3027500.
```

## MCP Backend

Use `mcp` for the original tree-like NIfTI skeletonization method integrated as a SkelHub backend.

### CLI

```bash
skelhub run --algorithm mcp --input input.nii.gz --output out.nii.gz
```

With custom parameters:

```bash
skelhub run --algorithm mcp --input input.nii.gz --output out.nii.gz \
    --root-method max_fdt \
    --threshold-scale 1.0 \
    --dilation-factor 2.0 \
    --max-iterations 200 \
    --min-object-size 50 \
    --label-objects \
    --verbose
```

### Parameters

- `--root-method {max_fdt,topmost}`: choose each object's root voxel. Default: `max_fdt`.
- `--threshold-scale FLOAT`: multiply the branch-significance threshold. Default: `1.0`.
- `--dilation-factor FLOAT`: scale the FDT-based dilation radius. Default: `2.0`.
- `--max-iterations INT`: cap outer skeleton-growth iterations per object. Default: `200`.
- `--min-object-size INT`: ignore smaller connected components. Default: `50`.
- `--label-objects`: write connected-component labels instead of binary `1` values.
- `--verbose`: print progress and runtime summaries.

### Notes and Limits

- MCP is inspired by Jin et al. for tree-like 3D objects.
- The flow includes multi-object decomposition, FDT, LSF, geodesic distance, minimum-cost paths, and scale-adaptive dilation.
- MCP-specific orchestration remains under `skelhub/algorithms/mcp/`.
- The framework core consumes only the standardized backend result.

### Citation

```text
D. Jin, K. S. Iyer, C. Chen, E. A. Hoffman, and P. K. Saha, "A robust and efficient curve skeletonization algorithm for tree-like objects using minimum cost paths," *Pattern Recognition Letters*, vol. 76, pp. 32-40, Jun. 2016, doi: 10.1016/j.patrec.2015.04.002.
```

## Lee94 Backend

Use `lee94` for scikit-image's Lee et al. 1994 3D thinning implementation through the SkelHub interface.

### CLI

```bash
skelhub run --algorithm lee94 --input input.nii.gz --output out.nii.gz
```

With thresholding:

```bash
skelhub run --algorithm lee94 --input input.nii.gz --output out.nii.gz \
    --binarize-threshold 0.5 \
    --verbose
```

### Parameters

- `--binarize-threshold FLOAT`: threshold normalized input intensities before skeletonization. Default: `0.5`.

### Notes and Limits

- The backend wraps `skimage.morphology.skeletonize(..., method="lee")`.
- The adapter validates 3D input, thresholds it, and returns `SkeletonResult`.
- The wrapped scikit-image implementation already handles its own zero padding.
- Lee94 behavior is isolated under `skelhub/algorithms/lee94/`.

### Citation

```text
T. C. Lee, R. L. Kashyap, and C. N. Chu, "Building Skeleton Models via 3-D Medial Surface Axis Thinning Algorithms," *CVGIP: Graphical Models and Image Processing*, vol. 56, no. 6, pp. 462-478, Nov. 1994, doi: 10.1006/cgip.1994.1042.
```

## L1 Skeleton Backend

*Review pending:* this backend and its documentation need further review before being treated as a primary recommended path.

Use `l1_skeleton` for a Python-native L1-medial skeleton path based on point-cloud contraction and branch rasterization.

### CLI

```bash
skelhub run --algorithm l1_skeleton --input input.nii.gz --output out.nii.gz
```

With custom parameters:

```bash
skelhub run --algorithm l1_skeleton --input input.nii.gz --output out.nii.gz \
    --l1-sample-count 512 \
    --l1-initial-radius 2.0 \
    --l1-max-radius 8.0 \
    --l1-max-iterations 80 \
    --verbose
```

### Parameters

- `--l1-sample-count`: limit moving samples seeded from foreground voxels.
- `--l1-initial-radius`, `--l1-radius-growth`, `--l1-max-radius`: control the local neighborhood schedule.
- `--l1-max-iterations`, `--l1-stop-error`: control contraction convergence.
- `--l1-repulsion-mu`, `--l1-repulsion-mu-min`: control conditional repulsion.
- `--l1-random-seed`: make sampling deterministic.
- `--l1-output-mode {branches,points}`: choose branch-curve rasterization or contracted-point output.
- `--l1-use-density-weighting` / `--no-l1-use-density-weighting`: toggle inverse local-density weighting.
- `--l1-use-recentering` / `--no-l1-use-recentering`: toggle branch-local ellipse re-centering.

### Notes and Limits

- Foreground is `data > 0`; output is same-shape binary `uint8`.
- Foreground voxels are converted to point coordinates using voxel spacing when available.
- The default output rasterizes final branch curves.
- `--l1-output-mode points` keeps the earlier contracted-sample output path available.
- The backend does not emit GraphML or attach a `GraphResult`.
- No original C++ source is copied; the local C++/Qt project is used for traceability only.

### Citation

```text
H. Huang *et al.*, "L1-medial skeleton of point cloud," *ACM Transactions on Graphics*, vol. 32, no. 4, pp. 1-8, Jul. 2013, doi: 10.1145/2461912.2461913.
```

## Palagyi-Kuba Backend

*Review pending:* this backend and its documentation need further review before being treated as a primary recommended path.

Use `palagyi_kuba` for a Python-native 12-subiteration 3D thinning backend with curve or surface modes.

### CLI

```bash
skelhub run --algorithm palagyi_kuba --input input.nii.gz --output out.nii.gz
```

With custom parameters:

```bash
skelhub run --algorithm palagyi_kuba --input input.nii.gz --output out.nii.gz \
    --pk-mode surface \
    --pk-binarize-threshold 0.5 \
    --pk-max-cycles 20 \
    --verbose
```

### Parameters

- `--pk-mode {curve,surface}`: choose curve endpoint preservation or surface endpoint preservation.
- `--pk-binarize-threshold FLOAT`: threshold non-binary input before thinning. Default: `0.5`.
- `--pk-max-cycles INT`: optionally cap full 12-direction thinning cycles.

### Notes and Limits

- Axis convention: axis0 = U/D, axis1 = N/S, axis2 = W/E.
- Subiteration order: `US, NE, DW, SE, UW, DN, SW, UN, DE, NW, UE, DS`.
- Template tables are encoded from local Palagyi-Kuba reference figures.
- Output is same-shape binary `uint8`.
- The backend does not attach a graph result.

### Citation

```text
K. Palagyi and A. Kuba, "A Parallel 3D 12-Subiteration Thinning Algorithm," *Graphical Models and Image Processing*, vol. 61, no. 4, pp. 199-221, Jul. 1999, doi: 10.1006/gmip.1999.0498.
```

## Flux Backend

*Review pending:* this backend and its documentation need further review before being treated as a primary recommended path.

Use `flux` for Python-native flux-driven medial curve extraction on already-binary volumes.

### CLI

```bash
skelhub run --algorithm flux --input input.nii.gz --output out.nii.gz
```

With custom parameters:

```bash
skelhub run --algorithm flux --input input.nii.gz --output out.nii.gz \
    --flux-threshold 0.0 \
    --flux-sigma 0.5 \
    --flux-sigma-unit physical \
    --verbose
```

### Parameters

- `--flux-threshold FLOAT`: average-outward-flux endpoint preservation threshold. Default: `0.0`.
- `--flux-sigma FLOAT`: Gaussian smoothing sigma for the signed-distance image. Default: `0.5`.
- `--flux-sigma-unit {physical,voxels}`: interpret sigma in physical or voxel units. Default: `physical`.

### Notes and Limits

- Input must be exactly binary `{0, 1}`.
- Non-binary volumes are rejected instead of thresholded.
- The backend computes signed distance, smoothed gradients, 26-neighborhood average outward flux, and topology-preserving priority thinning.
- Output is same-shape binary `uint8`.
- The backend does not attach a graph result.
- No VMTK source is copied; the backend is Python-native and documents the VMTK/EvoLib reference path.

### Citation

```text
X. Mellado, I. Larrabide, M. Hernandez, and A. Frangi, "Flux driven medial curve extraction," *The Insight Journal*, Oct. 2010, doi: 10.54294/akkjqm.
```
