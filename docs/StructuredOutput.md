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

`EvaluationResult` records NIfTI or GraphML evaluation output (schema `3.0`, evaluation v3).

It includes:

- `input_representation`: `nifti` or `graphml`
- `status`: `ok`, `empty_prediction`, `empty_reference` or `both_empty`
- `geometry`: `tolerances` (one `ToleranceMatch` per requested tolerance, in order; `primary` is the first) with precision, recall and F1; supporting values are matched/unmatched prediction and reference **voxel counts** (NIfTI) or **lengths in µm** (`*_length_um`, GraphML), and the other family is `None`. `distances` (`DistanceSummary`, µm) or `None`; for GraphML, `hausdorff_is_approximate` is True and `sampling_error_bound_um` / `hausdorff_upper_bound_um` give the bound. Reasons when unavailable.
- `topology`: reference and prediction `BettiNumbers` (`beta_0`, `beta_1`, `beta_2`, Euler characteristic), `comparison(k)` and `betti_count_agreement`. Voxel connectivities are `None` for GraphML, whose topology comes from the stored edges (`beta_2` is structurally 0).
- `endpoints`: reference and prediction endpoint counts (NIfTI: voxels with one 26-neighbour; GraphML: degree-1 nodes) with signed and absolute difference
- `foreground_edt`: `ForegroundEdtAgreement` (reference and prediction `ForegroundEdtSummary`, `ForegroundMaskInfo` provenance, signed and absolute relative difference, warnings), or `None` when no foreground mask was supplied and always for GraphML (`foreground_edt_unavailable_reason`)
- `graph`: `GraphEvaluationInfo` for GraphML, else `None`: `coordinate_image` (`CoordinateImageInfo`: path, shape, units, spacing and affine in µm), `sampling` (`GraphSamplingInfo`: mode, requested and resolved step, rule, Hausdorff bound) and `prediction` / `reference` (`GraphInputSummary`: state, node/edge/isolated/self-loop/parallel counts, total length, segments, edge-path source, reversed paths, skipped repeats, points outside the image, length samples)
- `config`: requested and µm tolerances, connectivity or graph topology definition, and metric definitions (`skelhub-voxel-v2` or `skelhub-graph-v1`)
- `metadata`: paths, shape, spacing and affine in µm; NIfTI adds source units and foreground voxel counts, GraphML adds both curve lengths
- `warnings`

For metric details, see [Evaluation](evaluation.md).

## FeatureExtractionResult

`extract_features_from_paths(...)` returns edge rows, node rows, the
header-derived physical unit suffix, and non-fatal warnings such as a
Laplacian graph path that differs from the supplied skeleton volume.

## Current Output Files

- `skelhub run` writes a skeleton NIfTI volume.
- `skelhub run --algorithm laplacian --graph_output ...` can also write cleaned GraphML.
- `skelhub run --algorithm laplacian --graph_original ...` writes refined pre-cleaning GraphML whose edges include JSON `centerline_voxel_points`: unrounded, unclipped float samples along the straight source-to-target segment. The cleaned `--graph_output` export does not include this field.
- `skelhub evaluate --json-output ...` writes a structured JSON evaluation report (NIfTI or GraphML pairs; see [Evaluation](evaluation.md#report-structure)).
- `skelhub graphgen` writes a GraphML proto-graph from a skeleton NIfTI. Every
  edge's `centerline_voxels`, `centerline_voxel_points`, and
  `centerline_world_points` path is oriented from GraphML source to target and
  includes the corresponding incident node coordinates. Integer paths use
  rounded node positions and 26-connected endpoint connectors.
- `skelhub feature` writes separate edge and node CSV files from a binary vessel foreground, skeleton, and compatible GraphML graph.

Feature edge CSV base columns (`length`, `minRadius`, `avgRadius`,
`maxRadius`, and `curveness`) are measured in voxel coordinates. The added
`*_image_<unit>` distance and radius columns use foreground-header voxel
sizes, with unit suffixes such as `_mm`, `_um`, `_m`, or `_unknown`.
The feature node CSV contains `id,position_x,position_y,position_z,degree`,
where positions are voxel coordinates and degree is the GraphML incidence
count.
