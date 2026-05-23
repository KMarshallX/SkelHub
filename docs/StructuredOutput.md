# Structured Output

SkelHub uses framework-level result containers so backends can differ internally without changing the public contract.

*Review pending:* this structure is usable now, but it will be reviewed as SkelHub grows beyond the current backend set.

## SkeletonResult

Every backend returns a `SkeletonResult`.

It stores:

- `algorithm_name`: backend name, such as `laplacian` or `mcp`
- `skeleton`: output voxel array
- `input_metadata`: source volume details
- `runtime_stats`: timing and run-level statistics
- `warnings`: recoverable issues or degraded-output notices
- `backend_metadata`: controlled backend-specific metadata
- `graph`: optional `GraphResult`

Backend metadata is namespaced by algorithm where practical:

- `result.backend_metadata["laplacian"]`
- `result.backend_metadata["mcp"]`
- `result.backend_metadata["lee94"]`
- `result.backend_metadata["l1_skeleton"]`

## GraphResult

`GraphResult` is the shared graph container for framework-level graph data.

It stores:

- `nodes`
- `edges`
- `metadata`

Graph extraction should stay in postprocessing unless a backend is naturally graph-native.

## EvaluationResult

`EvaluationResult` records voxel-based v1 evaluation output.

It includes:

- `TP`, `FP`, `FN`
- completeness `Cp`
- correctness `Cr`
- raw, clipped, and normalized `OCC`, `BCC`, and `E`
- global score `P`
- buffer radius metadata
- connectivity metadata
- warnings

For metric details, see [Evaluation](evaluation.md).

## Current Output Files

- `skelhub run` writes a skeleton NIfTI volume.
- `skelhub run --algorithm laplacian --graph_output ...` can also write cleaned GraphML.
- `skelhub run --algorithm laplacian --graph_original ...` can write the refined pre-cleaning GraphML.
- `skelhub evaluate --json-output ...` writes a structured JSON evaluation report.
- `skelhub graphgen` writes a GraphML proto-graph from a skeleton NIfTI.
