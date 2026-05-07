# Algorithms

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
