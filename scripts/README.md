# SkelHub Scripts

Helper scripts in this directory assume they are run from an installed checkout
with SkelHub available in the execution environment. `run_algo.sh` and
`run_graphgen.sh` use the currently activated conda environment and halt if
required dependencies are missing. Older wrappers may still activate the local
`Tools/SkelHub/.venv` before calling SkelHub commands or Python helpers.

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
and one cropped GraphML patch per affected connected component.

```bash
./scripts/crop_escaping_graph_patches.sh \
  --input-fore ./test_data/exvivo/foreground.nii.gz \
  --input-graph ./test_outputs/exvivo/original.graphml \
  --nif-path ./test_data/exvivo/patches \
  --grapa-path ./test_outputs/exvivo/patch_graphs
```

Required:

- `--input-fore`: foreground NIfTI used for confinement checks and connected components.
- `--input-graph`: primary GraphML checked for escaping nodes.
- `--nif-path`: output directory for cropped NIfTI patches.
- `--grapa-path`: output directory for cropped GraphML patches.

Optional:

- `--input-img`: crop a matching original/intensity NIfTI by the same boxes.
- `--input-skel`: crop a matching skeleton NIfTI by the same boxes.
- `--input-graph2`: crop a second GraphML by the same boxes.

Foreground patches are masked to contain only the affected component. Optional
image and skeleton patches are raw bbox crops. NIfTI patch affines include the
crop offset, while cropped GraphML coordinates remain in full-volume space.
