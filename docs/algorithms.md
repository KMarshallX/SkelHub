# Algorithms

SkelHub backends all run through the same command shape:

```bash
skelhub run --algorithm <name> --input input.nii.gz --output out.nii.gz
```

Each backend stays isolated under `skelhub.algorithms.<name>`.

## Contents

- [Laplacian Backend](#laplacian-backend)
- [laplskel Backend](#laplskel-backend)
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
    --stop_param 0.0015 \
    --n_free_iteration 0 \
    --area_param 50.0 \
    --poly_param 10 \
    --verbose
```

### Parameters

- `--graph_output PATH`: write the cleaned graph after `post_node_cleaning()`. Default: `None`. Supplying a path creates an aggregate GraphML for all processed components; omitting it skips this export.
- `--graph_original PATH`: write the refined graph before `post_node_cleaning()`. Default: `None`. Supplying a path creates the aggregate GraphML used for rasterizing the standard NIfTI output; omitting it skips this export. Each exported edge includes `centerline_voxel_points`, a JSON array of unrounded, unclipped float voxel coordinates sampled along the straight source-to-target segment. The sampling includes both exact node positions and uses `ceil(max(abs(end - start))) + 1` points for a non-degenerate edge; a zero-length edge stores one point.
- `--speed_param FLOAT`: contraction anchoring weight for each node's current position. Default: `0.05`. Larger values resist movement and can make contraction more conservative or slower; smaller values allow stronger movement toward the graph constraints and can collapse geometry more aggressively.
- `--dist_param FLOAT`: weight for distance-normalized neighbor smoothing in the Laplacian system. Default: `0.5`. Larger values increase neighbor-position smoothing and straightening; smaller values reduce this smoothing influence.
- `--med_param FLOAT`: weight for medial/radius-guided neighbor attraction. Default: `0.5`. Larger values make local radius information more influential during contraction; smaller values make contraction depend less on the distance-transform radius field.
- `--degree_threshold FLOAT`: angle tolerance used to mark already-skeletal nodes. Default: `5.0`. Larger values classify more near-collinear nodes as skeletal, preserving more local structure during topology updates; smaller values are stricter and allow more nodes to keep contracting and clustering.
- `--sampling FLOAT`: sampling factor for the initial dense graph. Default: `1.0`. Larger values downsample the input before graph construction, reducing nodes and runtime but making the graph coarser; smaller values upsample, increasing detail, memory use, and runtime.
- `--clustering_r FLOAT`: spatial radius used when contracted moving nodes are clustered into topology updates. Default: `1.0`. Larger values merge nearby nodes more readily and simplify topology faster; smaller values keep more nodes separate and can preserve detail at higher cost.
- `--stop_param FLOAT`: convergence scale applied to the initial cumulative small-cycle polygon area. Default: `0.0015`. Larger values loosen the convergence target and usually reduce contraction iterations; smaller values require lower residual cycle area and can increase quality pressure, runtime, and hard-limit hits.
- `--n_free_iteration INT`: number of initial contraction iterations before convergence checks may stop the loop. Default: `0`. Larger values force more contraction iterations even if the stop criterion is already met; smaller values allow earlier stopping.
- `--area_param FLOAT`: area threshold for post-contraction small-polygon refinement. Default: `50.0`. Larger values refine/collapse more polygon artifacts; smaller values refine only smaller cycles and preserve more local graph structure.
- `--poly_param INT`: upper cycle-size limit for post-contraction polygon refinement. Default: `10`. Larger values include longer cycles in refinement; smaller values restrict refinement to shorter cycles.
- `--verbose`: show connected-component processing progress, elapsed time, and estimated remaining time. Default: disabled. Enabling it prints progress logs but does not change algorithm output.
- Per-component's max contraction iteration is empirically hardcoded to be `750`. If the max cap is hit, a warning will be thrown and the contraction will stop and return the contracted results.

### Notes and Limits

- The backend is graph-native internally.
- SkelHub still returns a standard binary skeleton NIfTI.
- Foreground input is decomposed into 26-connected components before Laplacian contraction; each component is processed independently and merged into the final outputs.
- The standard NIfTI output is rasterized from `graph_original`.
- Degree-2 chains use quadratic Bezier interpolation before 26-connected voxel path filling.
- The `graph_original` GraphML keeps straight continuous edge samples in `centerline_voxel_points`. This field describes the graph's native per-edge geometry; it does not replace the separate quadratic-Bezier rule used to rasterize the NIfTI output.
- If one component reaches the Laplacian contraction iteration cap, SkelHub warns and continues with that component's latest contracted graph.
- `--graph_output` writes one aggregate cleaned graph; `--graph_original` writes one aggregate refined graph used for rasterization.
- Both exports can be compared with `skelhub evaluate` as GraphML pairs, with the input NIfTI as `--coordinate-image`. `--graph_original` edges use their stored `centerline_voxel_points`. `--graph_output` edges store no `centerline_voxel_points`, so evaluation uses each straight node-to-node segment and warns. A zero-length edge (stored as one point) makes evaluation reject the file. See [Evaluation](evaluation.md#graphml-inputs-and-sampling).

### Citation

```text
R. Damseh, P. Delafontaine-Martel, P. Pouliot, F. Cheriet, and F. Lesage, "Laplacian Flow Dynamics on Geometric Graphs for Anatomical Modeling of Cerebrovascular Networks," *IEEE Transactions on Medical Imaging*, vol. 40, no. 1, pp. 381-394, Jan. 2021, doi: 10.1109/TMI.2020.3027500.
```

## laplskel Backend

EDT-guided anisotropic contraction with hard foreground containment, then topology-preserving thinning, then an optional second fit that smooths node positions. (Underdevelopment, preprint will be ready soon)

### CLI

```bash
skelhub run --algorithm laplskel --input mask.nii.gz --output skeleton.nii.gz
```

All options, at their defaults except the second fit:

```bash
skelhub run --algorithm laplskel \
    --input mask.nii.gz --output skeleton.nii.gz \
    --graph_output skeleton.graphml --graph_original contracted.graphml \
    --w_L 0.5 --w_H 0.5 --w_H_medial 20 --beta_edt 1 \
    --max_iter 500 --tol_max_drift 0.05 --tol_mean_drift 0.0025 \
    --decimate_ratio 0.93 --dec_grid_size 0.01 \
    --second_fitting --fit_w_H 0.16 --fit_w_H_medial 3 \
    --init_graph_adj 26 --local_pca_hops 1 --label_connectivity 26 \
    --solver CG --n_jobs 1 --verbose
```

### Outputs

- `--output` (always): the digital skeleton NIfTI on the input grid, written once by SkelHub. Every voxel of the topology-preserving thinning result is set. The second fit does not change it.
- `--graph_output PATH` (optional): the final skeleton graph. It has one node per skeleton voxel, joined by straight edges that keep every foreground tunnel. Node coordinates are the fitted positions with `--second_fitting`, or voxel centres without it. Edge paths are stored too.
- `--graph_original PATH` (optional): the contracted graph before thinning, i.e. the raw result of the contraction stage.
- Each graph path picks its format by suffix and is independent of the other:
  - `.graphml`: GraphML with `voxel_pos`, world `X/Y/Z`, `centerline_voxel_points` (float edge path) and `centerline_voxels` (integer voxel path).
  - `.npz`: the sparse adjacency in `PATH`, plus `<stem>_coords.npz` beside it with `contracted_X` (node coordinates). For `--graph_output` the sidecar also holds `edge_path_nodes`, `edge_path_offsets` and `edge_path_points`.
- Suffixes and clashes between all output files (including `_coords.npz` sidecars) are checked before any computation. Missing output folders are created.

### Parameters

- `--w_L` (0.5): Laplacian (contraction) weight, α. Shared with the second fit.
- `--w_H` (0.5): baseline retention weight, β.
- `--w_H_medial` (20): retention boost at inscribed-sphere centres, raised to each node's medialness. 1 disables it.
- `--beta_edt` (1): EDT scale in the retention weight $w_H \exp(\beta_{\mathrm{edt}}/(d + 0.5))$, where $d$ is the distance to the boundary. Shared with the second fit.
- `--max_iter` (500), `--tol_max_drift` (0.05 voxel), `--tol_mean_drift` (0.0025 voxel): iteration cap and stop rules (three steady steps), shared with the second fit. `--tol_max_drift` is also the small-step decimation threshold; `--tol_mean_drift 0` disables the mean test.
- `--decimate_ratio` (0.93, in (0, 1]): decimate once three consecutive mean-drift ratios lie in [ratio, 1].
- `--dec_grid_size` (0.01 voxel): largest merge-cluster diameter in decimation.
- `--second_fitting` (off): smooth degree-two node positions with the same flow, endpoints and junctions pinned, solver fixed to LU, no merging.
- `--fit_w_H` (0.16), `--fit_w_H_medial` (3): the second fit's own retention weights. Giving either without `--second_fitting` is an error.
- `--init_graph_adj` (26): voxel connectivity of the initial graph (6, 18 or 26).
- `--local_pca_hops` (1): graph hops in each local tangent estimate.
- `--separate_streams` (off), `--label_connectivity` (26): skeletonise each connected component separately. Connectivity must be 26 with `--separate_streams`.
- `--solver` (CG): contraction solver, `LU`, `CG` or `AMGCG`. AMGCG without `pyamg` falls back to CG with a warning.
- `--n_jobs` (unset): parallel component workers; unset or ≤ 0 uses about 30% of the cores.
- `--verbose`: print laplskel's progress (iterations, decimation, fit summary). Output files are the same either way.

### Notes and Limits

- **Mask reading differs from SkelHub's reader.** Mask reading uses `get_fdata()`, squeezes singleton axes, requires 3D and treats every non-zero voxel as foreground (negative values and NaN included). SkelHub's reader rescales non-binary values to [0, 1], which can change the mask. So the backend re-reads the input file in a different way. It first checks the `VolumeData` still matches that file and stops with an error if not. If the rescaled view would have given a different mask, the result carries a warning with the voxel count. With `VolumeData.path=None`, the in-memory array is the mask (non-zero = foreground).
- An empty mask is an error; it does not return an empty skeleton.
- A foreground with enclosed cavities is rejected: a curve graph cannot keep them.
- Spacing is read but not used: all stages work in voxel units.
- Graph files are written inside the backend; the NIfTI is written by the framework afterwards.
- `SkeletonResult.graph` holds rounded node positions; exact coordinates are in the graph files.
- Python warnings (for example a contraction reaching `--max_iter`) are copied into `SkeletonResult.warnings` and still shown. With `--n_jobs` > 1 and several components, warnings raised in worker processes are not collected.

### Citation

```text
_To be ready_
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

- `--root-method {max_fdt,topmost}`: choose each object's root voxel. Default:`max_fdt`. `max_fdt` starts from the foreground voxel with the greatest distance-transform value and usually favors a thick, well-centered root;`topmost` starts from the uppermost foreground-center maximal-ball voxel and is useful when the first array axis has a meaningful anatomical direction. Changing the root can change branch discovery order and the resulting tree.
- `--threshold-scale FLOAT`: multiply the branch-significance threshold. Default: `1.0`. Larger values reject more low-significance branches, usually producing a sparser skeleton with fewer noise spurs and less work, but may omit real short or weak branches. Smaller values accept more branches, increasing sensitivity and skeleton density at the cost of more spurs and runtime.
- `--dilation-factor FLOAT`: scale the FDT-based dilation radius. Default:`2.0`. Larger values mark a wider foreground region as covered around the root and each accepted path, usually reducing later branches and iterations but potentially suppressing nearby valid branches. Smaller values mark a narrower region, preserving more candidate branches and detail while increasing runtime and the risk of redundant or noisy branches.
- `--max-iterations INT`: cap outer skeleton-growth iterations per object. Default: `200`. Larger values allow more opportunities to cover complex objects and can improve completeness, but increase worst-case runtime. Smaller values finish sooner but can return a partial skeleton when the cap is reached; `0` prevents branch-growth iterations after root initialization.
- `--min-object-size INT`: ignore smaller connected components. Default: `50`. Larger values remove more small components, reducing noise and runtime but potentially discarding small vessels. Smaller values retain more components and detail while increasing sensitivity to isolated noise and processing cost; `0` keeps every non-empty component.
- `--label-objects`: write connected-component labels instead of binary `1` values. Default: disabled. Enabling it preserves the skeleton geometry but writes each object's component label; leaving it disabled produces a binary skeleton.
- `--verbose`: print progress and runtime summaries. Default: disabled. Enabling it adds logging without changing skeletonization results; leaving it disabled keeps command output concise.

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
