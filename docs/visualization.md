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

GraphML files render as lightweight points and lines so loaded vessel graphs
remain responsive while rotating, zooming, and panning.

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

- switch between `Single View` and `Double View` layout modes
- enable or disable world-coordinate camera synchronization across loaded files
- enable GraphML Interactive mode and inspect selected node `X`/`Y`/`Z`, node id, and node degree
- import more files
- close the active file
- move between loaded files
- reset the camera
- fit the active preview to the window without changing camera angle
- adjust Node Size and Edge Thickness with sliders
- scroll when the window is too short to show every panel control

`Single View` is the default and preserves the existing one-file workflow.
`Double View` splits the scene into `View A` and `View B`. `View A` starts
with the current active file, while `View B` starts empty. In double-view
mode, the top-left loaded-file dropdown is hidden and files are assigned from
the Tools panel `View A` / `View B` dropdowns, which can choose either `Empty`
or any loaded file. Clicking inside a viewport makes that viewport active,
and the Tools panel edits only that active viewport. `Import` loads a file
into the global loaded-file list and assigns it to the active viewport;
`Close` clears only the active viewport assignment in double-view mode.

For GraphML rendering, Node and Edge control on-screen point size and line
width without rebuilding graph geometry. Slider edits commit when the slider
is released. In double-view mode, appearance settings are per-view: changing
Node Size or Edge Thickness in `View A` does not change `View B`. `Fit preview`
adjusts the camera distance to fit the active object in the active viewport
while preserving the current camera angle. When the active file is a NIfTI
volume, the `Apperance` section remains visible but its sliders are greyed
out and disabled.

When the right-side panel cannot visually contain every control, a scrollbar
appears on the panel's right edge. Drag the scrollbar thumb, or use the mouse
wheel while the pointer is inside the panel, to scroll the panel content.
Wheel events inside the panel are consumed by the panel and do not zoom the
viewport.

Interactive mode becomes available when the active file is GraphML. Enabling
it allows rendered nodes to be clicked; the selected node is highlighted in
`#03FFD9`, and the side panel displays its rendered `X`/`Y`/`Z` coordinates
GraphML node id, and node degree. The `X`, `Y`, `Z`, and `Node dgr` rows are
read-only. The `Node id` row accepts a GraphML node id and jumps to that node
when `Enter` is pressed; `Escape` cancels an edit. While Interactive mode is
enabled and a node is selected, the left and right arrow keys move to the
previous or next GraphML node in file order.

In double-view mode, Interactive mode is per-view. Selecting a node in
`View B` makes `View B` active, highlights only the selected node in `View B`,
and updates the Tools panel with `View B` node details. Returning to `View A`
restores `View A`'s last selected node details. Arrow-key navigation moves
through nodes only in the active view.

`Sync Camera` starts enabled. When selecting another loaded GraphML or NIfTI
file, the viewer restores the same absolute camera position, focal point,
orientation, angle, and zoom in displayed world coordinates. This allows
aligned NIfTI and GraphML scenes to be inspected in the same view; arbitrary
GraphML coordinates or unregistered datasets may not align usefully, in
which case camera synchronization can be turned off. With synchronization
enabled, `Reset View` on the active file becomes the shared world-coordinate
camera for later file switches. Switching to `Double View` forces `Sync Camera`
on. With synchronization enabled, camera orbit, wheel travel, reset, and fit
operations in the active viewport are copied to the other populated viewport.

Drag-and-drop accepts `.graphml`, `.nii`, and `.nii.gz`. SkelHub reads the
`vtkStringArray` filename payload from VTK's `DropFilesEvent`; availability of
the operating-system drop event still depends on the desktop VTK/PyVista
backend. Use `Import` when that backend does not expose file drops.

For GraphML and NIfTI files, the mouse wheel moves the camera toward or away
from the active object's displayed center instead of changing scene
magnification. The wheel step scales with the current camera-object distance:
far views move faster, and close views move slower. Left-click dragging in the
viewport orbits the camera around the active object center without translating
the rendered scene. When Interactive mode is enabled, left-clicking a GraphML
node selects it instead.

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
