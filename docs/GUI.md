# Graph Tools GUI (`skelhub gui`)

> **Under active development.** Tabs, layout, and behaviour may change between releases. The GUI is currently separate from [`skelhub graphviz`](visualization.md): they share some loading and rendering helpers, but not windows, sessions, or controls.

`skelhub gui` opens a standalone Linux desktop window (PySide6) that runs graph and skeleton tools on one dataset at a time. For how the tabs map onto the postprocessing modules, see [Postprocessing](postprocessing.md#graph-tools-gui).

## Install and launch

```bash
python -m pip install -e '.[gui]'
skelhub gui
```

- The `gui` extra adds PySide6, matplotlib, and pyvistaqt.
- The EDT Heat viewer needs a working OpenGL display.
- If `skelhub` and `python` come from different environments, use `python -m skelhub gui`.

## Window

- Five top tabs: **Clean**, **Check**, **Crop patches**, **TopoStats**, **EDT Heat**.
- One job runs at a time. While it runs, the tabs are disabled, and closing the window is refused.
- A progress panel shows the current stage. Stages with a measurable fraction show a percentage. Other stages, such as graph conversion, the exact cycle basis, and the EDT, show an animated bar instead.
- The run log opens with timestamps while a job runs. After a success it closes again (if it opened automatically); after a failure it stays open.
- Existing output files are listed and must be confirmed before they are replaced.
- Changing an input marks the tab's previous result as out of date.

## Clean

Contracts degree-2 nodes while keeping the ordered centreline paths.

- Inputs: input GraphML, output GraphML.
- Reports node and edge counts before and after, and how many degree-2 nodes were removed.
- Method: [Proto-graph Cleaning](postprocessing.md#proto-graph-cleaning).

## Check

Checks that a skeleton or graph stays inside a foreground volume.

- Inputs: foreground NIfTI; skeleton NIfTI or GraphML; connectivity (26, 18, or 6).
- Reports:
  - whether every skeleton voxel, or every graph node `voxel_pos`, lies inside the foreground
  - for GraphML, the same check for each available edge path field (`centerline_voxels`, `centerline_voxel_points`, `centerline_world_points`)
  - connected-component counts
- Uses the same checker as `scripts/checker.sh`.

## Crop patches

Crops foreground components that contain graph nodes lying outside the foreground.

- Required inputs: foreground NIfTI, primary GraphML, and output folders for foreground patches and graph patches.
- Optional inputs: an image NIfTI (with its own patch folder), a second GraphML, and rasterized graph patches (with their own patch folder).
- Before cropping, it scans for existing patch files and asks before replacing them.
- Uses the same cropper as `scripts/crop_escaping_graph_patches.py`.

## TopoStats

Topology summary of an undirected graph.

- Input: GraphML (used as supplied) or a skeleton NIfTI. A NIfTI is converted through graphgen and cached under `${XDG_CACHE_HOME:-~/.cache}/skelhub/`.
- Counts: components $C$, nodes $V$, edges $E$, and independent cycles $E - V + C$. Parallel edges and self-loops are kept.
- Histograms, stacked vertically: node degree, and vertices per cycle in an unweighted minimum cycle basis.
- Runs in a separate process. Counts and the degree histogram appear before the cycle basis finishes, and **Cancel TopoStats** stops the process. The exact cycle basis has no percentage or ETA; elapsed time and a log line every five seconds show it is still working.
- **Export Report** writes JSON, CSV, and PNG files. Nothing is written otherwise.

## EDT Heat

Shows how far each part of a skeleton sits from the foreground boundary, in physical units.

### Distance methods

Pick one under **Distance method**, next to Calculate. Hover the **?** icon for a short reminder.

| Method | Definition | Skeletons |
|---|---|---|
| Voxel EDT (default) | Distance from a voxel centre to the nearest background voxel centre. Read at skeleton voxels; trilinearly interpolated at graph nodes. | NIfTI and GraphML |
| Surface distance | Shortest distance from a node to the foreground's unsmoothed 0.5 isosurface: $d(p) = \min_{x \in S} \lVert p - x \rVert$, over triangle interiors, edges, and vertices. | GraphML only |

- NIfTI skeletons always use Voxel EDT, and the selector is disabled for them.
- For GraphML, the last chosen method is remembered during the session.
- The two methods differ by about half a voxel. Voxel EDT measures to background voxel *centres*; the 0.5 surface sits halfway between foreground and background centres.
- Within one vessel cross-section, either value peaks at the centreline. Across the whole skeleton, it mostly reflects local vessel radius.

Surface reconstruction:

- The surface is built by full-resolution marching cubes (Lewiner variant) at isovalue 0.5. There is no smoothing, decimation, hole filling, or capping.
- It covers every foreground/background interface, including cavity walls.
- It is placed with the full foreground affine (rotation, anisotropic spacing, translation).
- The mesh is built from the foreground bounding box plus one voxel of observed background, so crop edges add no boundaries. It is reused while the foreground file is unchanged.
- It is inferred from the segmentation, not the true anatomy: its accuracy is limited by the segmentation and its voxel size.

### Inputs and output

- Foreground: binary NIfTI (`.nii` / `.nii.gz`).
- Skeleton: binary NIfTI, or GraphML with node `voxel_pos`. Edges must have `centerline_voxel_points`.
- **Calculate** runs loading, checks, and the distance calculation in the background with the selected method. Progress shows the loading stages; the EDT, surface reconstruction, and distance queries have no percentage.
- NIfTI: one block per skeleton voxel, drawn at its physical size and orientation, coloured in discrete bands.
- GraphML: nodes coloured on a continuous gradient. Edges follow `centerline_voxel_points` and are always neutral grey; they draw the shape only and carry no distance samples.

### Controls

- Color preset: Viridis, Plasma, Inferno, Cividis.
- Color bands (2–16, NIfTI only): equal-width value ranges between the smallest and largest sample. If all samples are equal, one colour is used.
- Node size and edge thickness (GraphML only). NIfTI blocks keep their physical voxel size.
- **Reset / Fit view**. Drag rotates, Shift+drag pans, wheel or right-drag zooms.
- Click a voxel or node to see its distance, voxel position, and physical position, plus the node ID for GraphML. Dragging does not select.
- The legend title, selection details, status, and run log all name the method of the *displayed* result ("Voxel EDT (mm)" or "Surface distance (mm)"). The unit comes from the foreground header (mm, µm, m). If the header has no unit, the label says "unit unspecified"; it never assumes mm.
- The side panel collapses with **Controls ▸**.

Recalculation and caching:

- Colour and size changes reuse the calculated samples and keep the camera.
- Choosing another method does not clear the view. The status turns amber ("Showing … · … not yet applied") until you press Calculate.
- Recalculating the same file pair with another method keeps the camera, the appearance settings, and the selected node.
- Results are cached per file pair and method, so switching back to an already-calculated method is instant.
- Changing either input clears the view and the cache.

### Checks before calculation

A failed check shows a warning, and nothing is drawn. Nothing is silently projected, resampled, or switched to the other method.

Both methods:

- Both files exist, are 3D and finite, and contain only the values 0 and 1.
- The foreground is not empty and not entirely foreground (without background, there is no distance).
- The foreground grid is not sheared. Rotated grids are fine; spacing-only EDT would be wrong on sheared ones.
- NIfTI pair:
  - same shape
  - the two affines place every corner voxel within 0.001 voxel of each other
  - the skeleton is not empty, and every skeleton voxel is inside the foreground
  - nothing is resampled or registered
- GraphML:
  - every node lies in an occupied foreground voxel cell. This is the checker's rule: voxel $i$ covers $[i - 0.5,\ i + 0.5]$ on each axis, and touching cells count.
  - edge paths stay inside the volume extent
  - if the file stores X/Y/Z or `centerline_world_points`, they must match the foreground affine applied to the voxel coordinates
- All geometry is placed with the foreground affine.

Surface distance adds:

- Every axis has at least 2 voxels, and marching cubes produces triangles.
- Every node lies within the voxel-centre hull, $0 \le$ `voxel_pos` $\le n - 1$ on each axis. The outer half-voxel strip passes the voxel-cell check, but the observed surface does not cover it, so containment there cannot be determined.
- Every node lies inside the reconstructed surface. The surface cuts across voxel cells at edges and corners, so a node can be inside a foreground voxel cell yet outside the surface. The warning says so and suggests Voxel EDT.
- A node within $10^{-6} \times$ the smallest voxel spacing of the surface counts as on it, with distance 0.

Where the foreground reaches the image border:

- The calculation runs.
- The surface is left open there, and a warning in the status and run log says distances are measured to the observed surface only; an unobserved boundary beyond the image could be closer.
- Inside/outside is decided with a separate, closed copy of the surface (the image padded with background). That copy matches the open surface within the voxel-centre hull. Its caps lie outside the hull and never contribute to a distance.

### Limitations

- The checks show that both files fit the same grid. They cannot prove the files came from the same source data.
- Interpolated Voxel EDT values estimate the distance between voxel centres; they are not distances to a surface.
- Surface distance follows the staircase-like marching-cubes surface of the voxel mask, and marching cubes resolves ambiguous diagonal contacts by its own rule. Nodes exactly at such contacts may be rejected as outside.
- Surface distance currently supports GraphML only.
- Distance queries run node by node. Very large graphs (hundreds of thousands of nodes) take noticeably longer.
- Only the sampled values are cached; the full EDT volume is not kept. Only the most recent foreground surface is kept.
- Large skeleton NIfTI files draw many instanced blocks, and there is no voxel-count warning yet.
- Without a working OpenGL display, the tab explains why the viewer is unavailable.
