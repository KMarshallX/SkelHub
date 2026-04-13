# Algorithms

## MCP Backend

The original repository content is now integrated as the first SkelHub backend under `skelhub.algorithms.mcp`.

Framework-facing usage:

```bash
# Run with default parameters:
skelhub run --algorithm mcp --input input.nii.gz --output out.nii.gz
# Run with custom parameters:
skelhub run --algorithm mcp --input input.nii.gz --output out.nii.gz \
    --root-method topmost \
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
- `--threshold-scale FLOAT` multiplies the branch-significance acceptance threshold. The default is `1.0`.
  Increase it to make branch acceptance more conservative and reduce weak side branches. Decrease it slightly to keep more marginal branches. The value must be positive.
- `--dilation-factor FLOAT` scales the FDT value used when generating the marked-mask dilation around the root and accepted branches. The default is `2.0`.
  Leaving it unset preserves the current behavior, where the dilation radius is `2 * FDT(p)` at each branch voxel. The value must be positive.
- `--max-iterations INT` sets the maximum number of outer skeleton-growth iterations per object. Default: `200`.
  This is a safety cap for complex or pathological inputs. If the cap is reached, the program stops growing that object safely and reports it in verbose mode.
- `--min-object-size INT` ignores connected components smaller than the given voxel count. Default: `50`.
  This is useful for filtering out isolated specks or segmentation noise before skeletonization begins.
- `--label-objects` writes each object's skeleton voxels using its connected-component label instead of writing all skeleton voxels as `1`.
  This is useful when the input volume contains multiple disconnected trees and you want to keep them distinguishable in the output.
- `--verbose` prints progress and runtime reporting during processing.

Implementation notes:

- The algorithm implements NIfTI-based curve skeletonization inspired by Jin et al. for tree-like 3D objects.
- The current code path includes multi-object decomposition, FDT and LSF computation, geodesic distance, minimum-cost path extraction, local scale-adaptive dilation, and Milestone 7 reporting behavior.
- Verbose MCP execution reports object counts, per-object iterations, branches added per iteration, branch counts, and runtime summaries.
- The MCP mathematics and intended growth-loop behavior are preserved from the pre-refactor code path.
- MCP-specific orchestration remains isolated in `skelhub/algorithms/mcp/multi_object.py`.
- The framework core does not depend on MCP internals; it only consumes the standardized result object returned by the backend adapter.
