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
  --node_size 7 \
  --edge_geometry continuous
```

## Inputs

### GraphML

GraphML nodes must contain usable spatial metadata.

SkelHub's current GraphML export writes coordinates as:

- `X`
- `Y`
- `Z`

If coordinates are missing, the viewer fails clearly instead of guessing a layout.

GraphML edge rendering supports:

- `straight`: one line between each edge's `X/Y/Z` endpoints; this remains the
  default and does not require edge data attributes
- `continuous`: a polyline following float `centerline_voxel_points`
- `voxel`: a line through the voxel centres in `centerline_voxels`

The two path attributes are stored in voxel coordinates. For curved modes,
the loader infers one affine from node `voxel_pos` and `X/Y/Z` pairs, validates
that relationship, and transforms every path point into the same world space
used by node and NIfTI rendering. If an attribute is absent or malformed, or
the node pairs cannot determine a valid 3D affine, its dropdown option is
disabled and the viewer displays the reason. An explicitly unavailable CLI
selection fails with a clear error instead of silently using straight edges.

All three modes render as lightweight points and lines so loaded vessel graphs
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

- switch between `Single View`, `Double View`, and `Overlay View` layout modes
- enable or disable world-coordinate camera synchronization across loaded files
- enable GraphML Interactive mode and inspect selected node `X`/`Y`/`Z`, node id, and node degree
- import more files
- close the active file
- move between loaded files
- reset the camera
- fit the active preview to the window without changing camera angle
- adjust Node Size and Edge Thickness with sliders
- select Straight, Continuous, or Voxel Path edge geometry under Appearance
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
Each viewport keeps its own complete camera state when its assigned file is
changed, including position, focal point, orientation, clipping range,
projection, viewing angle, and zoom. The replacement file is not fitted or
recentered automatically, even when it lies outside the preserved view.

`Overlay View` draws a Base file and an Overlay file in the same viewport.
Changing either layer preserves that viewport's complete camera state without
fitting or recentering the replacement file.
Its top bar displays the two filenames on separate full-width lines. A
filename that is wider than its line scrolls continuously so the complete
name remains discoverable. The Tools-panel Base and Overlay selectors reserve
more width for their filenames, matching the usable width of the open menu
rows. An overflowing filename in an open file menu scrolls only while that
menu row is hovered. Both top-bar rows are vertically centered within the
header boundary.

For GraphML rendering, the Geometry dropdown appears above Node Size and Edge
Thickness. In an overlay containing two graphs, it appears below `Target` and
controls the selected graph layer. Opening either dropdown reserves space
below it, moving later controls out of the menu's clickable area. Unavailable
geometry rows are greyed out; opening the menu displays their validation
status. Node and Edge control on-screen point size and line width. Slider edits
commit when the slider is released. In double-view mode, appearance settings
are per-view: changing Geometry, Node Size, or Edge Thickness in `View A` does
not change `View B`. Geometry changes rebuild the selected graph's edge mesh in
Single, Double, and Overlay View. `Fit preview`
adjusts the camera distance to fit the active object in the active viewport
while preserving the current camera angle. When the active file is a NIfTI
volume, the `Appearance` section remains visible but its sliders are greyed out
and disabled.

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

`Sync Camera` starts enabled in Single View. Entering Double View disables it,
so `View A` and `View B` initially retain independent cameras. Enabling
`Sync Camera` copies the active viewport's complete camera state to the other
populated viewport; subsequent camera orbit, wheel travel, reset, and fit
operations remain synchronized. Arbitrary GraphML coordinates or unregistered
datasets may not align usefully and can be inspected with synchronization off.
`Reset View` and `Fit Preview` remain explicit framing actions and can alter
the active camera; ordinary file changes in Double or Overlay View cannot.

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
