# Visualization

SkelHub provides `skelhub graphviz` for quick 3D inspection of vessel graphs and binary skeleton volumes.

The viewer is lightweight and PyVista-based. It supports:

- GraphML files with node coordinates
- binary `.nii` and `.nii.gz` volumes
- empty startup, then in-viewer import
- multiple loaded files in one session

## CLI Usage

Open an empty viewer:

```bash
skelhub graphviz
```

Open a GraphML file:

```bash
skelhub graphviz \
  --input ./test_data/lsys_graph/Lnet_i4_0_tort_centreline.graphml
```

Open a binary NIfTI file:

```bash
skelhub graphviz \
  --input ./test_outputs/skelhub_mcp_small.nii.gz
```

Adjust GraphML appearance:

```bash
skelhub graphviz \
  --input ./test_data/lsys_graph/Lnet_i4_0_tort_centreline.graphml \
  --edge_thickness 2.5 \
  --node_size 7
```

## Inputs

### GraphML

GraphML nodes must contain usable spatial metadata.

SkelHub's current GraphML export writes coordinates as:

- `X`
- `Y`
- `Z`

If coordinates are missing, the viewer fails clearly instead of guessing a layout.

GraphML files with at least 1,000 nodes automatically use a dense rendering
mode: nodes display as lightweight points and edges as lightweight lines so
large graphs remain responsive while rotating, zooming, and panning. The
viewer marks these files as `GraphML Dense` in the file status label.

### NIfTI

NIfTI inputs must be:

- 3D
- binary
- exactly `{0, 1}`

Foreground voxels render as physical blocks in displayed world coordinates
obtained from the NIfTI affine. The affine transforms both voxel centres and
the shared cube geometry, preserving physical voxel scale, orientation, axis
permutations, and flips. The interactive viewer instances that transformed
cube at all foreground positions so dense volumes retain block appearance
without expanding repeated cube geometry in memory.

## In-Viewer Controls

The top-left loaded-file dropdown remains available for selecting loaded
files. A `Tools` button is visible in the top-right corner from startup and
remains visible at all times; it opens and closes a right-side tools panel.
The button is positioned against the initialized desktop window and the
button and panel stay aligned to the right edge when the window is resized.
The panel starts hidden.

The tools panel can:

- enable or disable world-coordinate camera synchronization across loaded files
- enable a movable crosshair cursor and edit its `X`, `Y`, and `Z` position
- import more files
- close the active file
- move between loaded files
- reset the camera
- refresh GraphML appearance after slider changes
- adjust Node Size and Edge Thickness with sliders or adjacent `-` / `+`
  buttons in `0.1` steps

For standard GraphML rendering, Node and Edge control 3D sphere and tube
sizes. In dense rendering mode, they control on-screen point size and line
width without rebuilding graph geometry. Slider and `-` / `+` edits are
preview values until `Refresh` is pressed. When the active file is a NIfTI
volume, the panel keeps its file/session buttons but hides the GraphML
appearance rows.

The cursor becomes available after a file is loaded. Enabling it initializes
one saved position for that file at the center of its rendered scene and
draws a crosshair in the viewport. Left-click and drag in the viewport to
move the cursor in the camera-facing plane through its current position, or
enter a finite numeric value in an `X`, `Y`, or `Z` field and press `Enter`.
`Escape` cancels a field edit. Each loaded file remembers whether its cursor
is enabled and its own cursor position; closing the Tools panel hides its
coordinate fields but leaves an enabled crosshair visible and movable.

Cursor values use the active file's displayed coordinates: GraphML uses its
rendered `X`/`Y`/`Z` coordinates, while NIfTI uses affine-derived physical
world coordinates. Cursor positions remain specific to each loaded file;
compatible coordinates coincide only when files share a meaningful displayed
world frame.

`Sync Camera` starts enabled. When selecting another loaded GraphML or NIfTI
file, the viewer restores the same absolute camera position, focal point,
orientation, angle, and zoom in displayed world coordinates. This allows
aligned NIfTI and GraphML scenes to be inspected in the same view; arbitrary
GraphML coordinates or unregistered datasets may not align usefully, in
which case camera synchronization can be turned off. With synchronization
enabled, `Reset View` on the active file becomes the shared world-coordinate
camera for later file switches.

Drag-and-drop accepts `.graphml`, `.nii`, and `.nii.gz` when the desktop VTK/PyVista backend exposes file drops.

When a GraphML file is active, the mouse wheel travels forward and backward
along the current camera direction without stopping at the original focal
point. This allows close inspection while moving through local graph
features. NIfTI files keep the standard PyVista wheel navigation behavior.

## HPC and Conda Notes

On HPC systems such as Bunya, prefer a conda environment:

```bash
conda activate skelhub
conda install -c conda-forge libstdcxx-ng
skelhub graphviz
```

If runtime libraries conflict, reset the module stack and point `LD_LIBRARY_PATH` at the active conda environment:

```bash
module unload Miniconda3
module load Miniconda3
conda activate skelhub
conda install -c conda-forge libstdcxx-ng
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
skelhub graphviz
```

If `skelhub` and `python` come from different environments, run:

```bash
python -m skelhub graphviz
```
