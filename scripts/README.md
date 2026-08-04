# SkelHub Scripts

Helper scripts in this directory assume they are run from an installed checkout
with SkelHub available in the execution environment. `run_algo.sh` and
`run_graphgen.sh` use the currently activated conda environment and halt if
required dependencies are missing. `crop_escaping_graph_patches.sh` also uses
the active conda environment and reports any missing Python packages before
running. Older wrappers may still activate the local
`Tools/SkelHub/.venv` before calling SkelHub commands or Python helpers.

## `protograph_cleaner.sh`

Contracts every degree-2 GraphML node into its adjacent centreline edges. The
former node position remains as one interior point in the merged edge path,
and separate paths between the same pair of retained nodes remain separate
parallel edges.

The precise `centerline_voxel_points` and node `voxel_pos` fields are the input
geometry. Existing `centerline_voxels` are ignored because separated graphs may
contain truncated or empty integer paths. Every output edge receives a newly
generated, non-empty, 26-connected `centerline_voxels` path and an updated
`num_centerline_voxels` value.

```bash
./scripts/protograph_cleaner.sh \
  --input ./test_data/exvivo/Aug/skel_vessyn_aug_protograph.graphml \
  --output ./scripts/test.graphml \
  --verbose
```

Required:

- `--input`, `-i`: readable `.graphml` with `voxel_pos`, edge
  `centerline_voxel_points`, and at least one degree-2 node.
- `--output`, `-o`: destination `.graphml` path. Missing parent directories
  are created.

Optional:

- `--verbose`, `-v`: show a progress bar over all input nodes and print graph
  counts after cleaning.

The script uses `python` from the active environment and checks for `igraph`,
NumPy, and SkelHub; it does not activate `.venv`. If the output exists, the
script prompts for confirmation. Only `y` or `yes` replaces the file.

## `checker.sh`

Checks whether all nonzero skeleton voxels are confined to nonzero voxels in a
foreground volume. Both inputs must be `.nii` or `.nii.gz` files with identical
shapes.

```bash
./scripts/checker.sh \
  --foreground ./foreground.nii.gz \
  --skeleton ./skeleton.nii.gz \
  --connectivity 26
```

Required:

- `--foreground`, `-f`: foreground NIfTI volume.
- `--skeleton`, `-s`: skeleton NIfTI volume.

Optional:

- `--connectivity`, `-c`: connectivity used to count foreground and skeleton
  components; one of `6`, `18`, or `26` (default: `26`).

The script prints whether all skeleton voxels are within the foreground,
followed by the connected-component count for each volume. If either input
contains values other than zero and one, its sorted unique non-binary values
are reported to stderr and all nonzero values are still included in both the
confinement check and component count.

## `run_algo.sh`

Batch-runs one SkelHub skeletonization backend over every `.nii` or `.nii.gz`
file under an input directory. Outputs mirror the input directory structure and
append a configurable suffix before the NIfTI extension.

```bash
./scripts/run_algo.sh \
  --algorithm laplacian \
  --input-dir ./test_data/exvivo \
  --output-dir ./test_outputs/exvivo \
  --graph_original ./test_outputs/exvivo/original.graphml
```

Required:

- `--algorithm`: backend name, such as `laplacian`, `mcp`, or `lee94`.
- `--input-dir`: directory searched recursively for NIfTI inputs.
- `--output-dir`: destination directory for skeleton outputs.

Useful options:

- `--suffix`: output suffix, default `_centreline`.
- `--no-verbose`: do not pass `--verbose` to `skelhub run`.
- Arguments after `--` are forwarded to `skelhub run`.

## `run_graphgen.sh`

Batch-generates GraphML proto-graphs from skeleton NIfTI files. The script
searches recursively under the input directory, preserves relative subdirectory
structure, and writes one `.graphml` file per `.nii` or `.nii.gz` skeleton.

```bash
./scripts/run_graphgen.sh \
  --input ./test_outputs/exvivo/mcp/selected \
  --output ./test_outputs/exvivo/mcp/graphs \
  --verbose
```

Required:

- `--input`, `-i`: directory searched recursively for skeleton NIfTI files.
- `--output`, `-o`: destination directory for generated GraphML files.

Useful options:

- `--verbose`, `-v`: pass `--verbose` to `skelhub graphgen`.

If the output directory does not exist, the script prints a notice and creates
it. If the path cannot be created or does not resolve to a directory, it prints
a warning and halts.

## `run_featext.sh`

Batch-extracts edge and node feature CSVs from matched foreground NIfTI,
skeleton NIfTI, and GraphML files. All three input directories are searched
recursively, while output CSVs are written directly into the two output
directories.

```bash
./scripts/run_featext.sh \
  --foreground-dir ./test_data/foregrounds \
  --skel-dir ./test_outputs/skeletons \
  --graph-dir ./test_outputs/graphs \
  --edge-op-dir ./test_outputs/features/edges \
  --node-op-dir ./test_outputs/features/nodes \
  --verbose
```

Required:

- `--foreground-dir`, `-fd`: directory searched for foreground `.nii` and `.nii.gz` files.
- `--skel-dir`, `-sd`: directory searched for skeleton `.nii` and `.nii.gz` files.
- `--graph-dir`, `-gd`: directory searched for `.graphml` files; it may be the same as `--skel-dir`.
- `--edge-op-dir`, `-eo`: destination for `<foreground-stem>_edge.csv` files.
- `--node-op-dir`, `-no`: destination for `<foreground-stem>_node.csv` files.

Optional:

- `--verbose`, `-v`: show matched paths and batch progress, and pass `--verbose` to `skelhub feature`.

For each foreground stem, the script prefers one exact skeleton stem match.
If there is no exact match, exactly one skeleton stem must contain the
foreground stem. The selected skeleton must then have exactly one GraphML with
the same stem. Matching is global across the directory trees. Missing or
ambiguous matches, duplicate foreground stems, and failed feature commands halt
the batch immediately with a nonzero exit status. Missing output directories
are created automatically; existing output CSVs may be replaced.

## `run_local_pca.sh`

Computes local principal components for a selected cluster of GraphML vessel
nodes. World coordinates (`X`, `Y`, `Z`) and voxel coordinates (`voxel_pos`)
are processed and reported separately.

```bash
./scripts/run_local_pca.sh \
  --input ./test_data/exvivo/July/oof/stef_out/component_0001_my_0729.graphml \
  --node_cluster '[n190, n191, n248]'
```

Required:

- `--input`, `-i`: readable, valid, non-empty `.graphml` vessel graph.
- `--node_cluster`, `-c`: one quoted bracketed list containing at least three
  unique node IDs. Every requested ID must occur exactly once in the graph.

For each coordinate system, the script centers the selected points and builds
the unnormalised scatter matrix
`C = sum((x - mean) (x - mean)^T)`. It does not divide `C` by `N` or `N-1`.
The report includes the centroid, matrix, eigenvalues in descending order, each
raw eigensolver eigenvector, and its normalized unit vector. NumPy's symmetric
eigensolver normally returns unit vectors already, so the raw and normalized
vectors generally match. It also reports `lambda_1/lambda_2`,
`lambda_2/lambda_3`, and `lambda_1/lambda_3`. A ratio is reported as `inf` when
its denominator is zero or numerically near zero. Eigenvector signs are
arbitrary.

Collinear or coplanar point clusters produce a warning but are still processed.
Effectively repeated eigenvalues also produce a warning because their
corresponding principal directions are underdetermined. Connectivity among the
selected nodes is not required.

## `run_eval.sh`

Batch-evaluates predicted skeleton NIfTI files against reference skeletons.
The script matches prediction/reference files by their `Lnet_i...` filename
prefix and passes each pair to `skelhub evaluate`.

```bash
./scripts/run_eval.sh \
  --pred-dir ./test_outputs/lsys_mcp \
  --ref-dir ./test_data/lsys_gt \
  --buffer-radius 1 \
  --buffer-radius-unit voxels
```

Required:

- `--pred-dir`: directory searched recursively for prediction NIfTI files.
- `--ref-dir`: directory searched recursively for reference NIfTI files.
- `--buffer-radius`: evaluation buffer radius.

Useful options:

- `--buffer-radius-unit`: `voxels` or `um`, default `voxels`.
- `--no-verbose`: do not pass `--verbose` to `skelhub evaluate`.
- Arguments after `--` are forwarded to `skelhub evaluate`.

## `crop_escaping_graph_patches.sh`

Finds GraphML nodes whose rounded `voxel_pos` falls outside a foreground NIfTI.
If escaping nodes are found, it writes one component-specific foreground patch
and one cropped GraphML patch per affected connected component. An optional
image input can be cropped to a separate output directory.

```bash
./scripts/crop_escaping_graph_patches.sh \
  --input-fore ./test_data/exvivo/foreground.nii.gz \
  --input-graph ./test_outputs/exvivo/original.graphml \
  --nif-path ./test_data/exvivo/foreground_patches \
  --grapa-path ./test_outputs/exvivo/patch_graphs \
  --rasterization \
  --skel-path ./test_outputs/exvivo/rasterized_patches
```

Required:

- `--input-fore`: foreground NIfTI used for confinement checks and connected components.
- `--input-graph`: primary GraphML checked for escaping nodes.
- `--nif-path`: output directory for cropped foreground NIfTI patches.
- `--grapa-path`: output directory for cropped GraphML patches.

Optional:

- `--input-img`: crop a matching original/intensity NIfTI by the same boxes.
- `--img-path`: output directory for cropped image NIfTI patches; required with `--input-img`.
- `--input-graph2`: crop a second GraphML by the same boxes.
- `--rasterization`: rasterize every cropped GraphML patch using the Laplacian
  backend's standard NIfTI-output rule.
- `--skel-path`: output directory for rasterized graph NIfTI patches; required
  with `--rasterization` and invalid without it.

The wrapper requires an active conda environment with `igraph`, `nibabel`,
`networkx`, `numpy`, `scipy`, and SkelHub. Missing packages are listed before
the helper exits.

If `--nif-path`, `--img-path`, `--grapa-path`, or an enabled `--skel-path`
does not exist,
the helper prints a yellow terminal warning and creates it. If creation fails,
the process fails.

Foreground patches are masked to contain only the affected component. Optional
image patches are raw bbox crops. NIfTI patch affines include the crop offset,
while cropped GraphML coordinates remain in full-volume space.

Rasterization follows `skelhub run --algorithm laplacian`: nodes and edges are
rasterized from graph `voxel_pos` values, degree-2 chains use quadratic Bezier
interpolation, and sampled paths are filled with 26-connected voxels. The
component is rasterized within its original foreground bbox and embedded in the
buffered patch. Outputs use the same prefix as their GraphML source:
`graph_component_label_....nii.gz` for `--input-graph` and
`graph2_component_label_....nii.gz` for `--input-graph2`.
