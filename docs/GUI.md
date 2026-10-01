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

- Six top tabs: **Clean**, **Check**, **Crop patches**, **TopoStats**, **EDT Heat**, **Evaluate**.
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

## Evaluate

Compares a predicted skeleton NIfTI with a reference skeleton, using the same evaluation as `skelhub evaluate`. For metric definitions and input rules, see [Evaluation](evaluation.md).

### Inputs and spatial units

- Select a **Prediction skeleton NIfTI** and a **Reference skeleton NIfTI** (`.nii` or `.nii.gz`) with **Browse…** or by typing a path.
- Each file's header is read when you pick it (or shortly after you stop typing). The voxel data is not loaded for this. Below each file you see its shape, the header unit, the effective unit and the voxel spacing in µm.
- **Spatial unit**, set separately for each file:
  - **Known header unit** (µm, mm or metres): filled in and locked, with "From NIfTI header." It cannot be overridden.
  - **Unknown header unit**: the dropdown starts at "Select spatial unit…" and **Evaluate** stays disabled until you choose. Afterwards it reads "User supplied; header unit is unknown."
  - **Unsupported unit code or non-3D file**: shown as an error, and evaluation stays unavailable.
- A unit choice labels the stored spacing and coordinate values; it does not change the spacing. Stored spacing 0.05 with mm gives 50 µm; 50 with µm gives 50 µm; 1 with µm gives 1 µm. Files are never modified.
- Choosing a different file clears that file's unit choice and preview.
- Shape differences are flagged before the run. Shape and affine mismatches are still rejected by the evaluation, and the error appears in a warning dialog.

### Tolerances

- **Tolerances**: one or more numbers separated by commas and/or spaces, for example `50, 100`. The field starts empty.
- The order is kept: the first value is the **primary** tolerance, and each tolerance is reported separately. Zero means exact matching. Negative, duplicate, non-finite and non-numeric values are rejected as you type.
- **Tolerance unit**: µm (default) or voxels. This unit is separate from the files' spatial units. Voxel tolerances need isotropic spacing; on anisotropic files the tab explains this and keeps **Evaluate** disabled until you choose µm.

### Results

- **Evaluate** runs as a background job with an animated progress bar and run-log messages.
- **Summary**:
  - status (Evaluated, Empty prediction, Empty reference, Both skeletons empty)
  - the primary tolerance
  - F1 at the primary tolerance, which is not an overall quality score
- **Tables**:
  - geometry coverage per tolerance (precision, recall, F1)
  - supporting matched and unmatched voxel counts
  - distances in µm (directional means, symmetric mean, symmetric P95, Hausdorff)
  - topology (β₀, β₁, β₂: reference, prediction, signed difference, absolute error) with **Betti-count agreement**
  - endpoint diagnostics
- **Unavailable values** show as **N/A**; hover to see the reason. They are never shown as zero.
- **Warnings**, including declared-unit provenance, appear above the tables and in the run log.
- **Outdated results**: changing a file, a declared unit, the tolerances or the tolerance unit marks the results "Results are outdated — run evaluation again." Changes to a file on disk are detected when you evaluate or export. A failed rerun keeps the old results marked as outdated.
- **Export JSON…** writes the same JSON report as `skelhub evaluate --json-output`, with full precision, warnings and unit provenance. It is enabled only for a current result, including empty-input results. An existing file is replaced only after you confirm.

## EDT Heat

Shows how far each part of a skeleton sits from the foreground boundary, in physical units, or how centred it is locally (the local EDT ratio).

**Colour by** picks what is shown:

- **Distance** (default): the physical distance from the chosen **Distance method** below.
- **Local EDT ratio**: a first centeredness indicator, described in [Local EDT ratio](#local-edt-ratio).

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

### Local EDT ratio

Compares the EDT at a skeleton point with the largest EDT close by. A centred point has the largest EDT in its neighbourhood.

For a skeleton point $p$ with Voxel EDT $D(p)$:

- search radius: $\rho(p) = \alpha \, D(p)$
- candidates: $Q(p) = \{\, q \text{ a foreground voxel centre} : \operatorname{comp}(q) = \operatorname{comp}(p),\ \lVert p - q \rVert \le \rho(p) \,\}$
- ratio: $r(p) = \dfrac{D(p)}{\max\left(\{D(p)\} \cup \{D(q) : q \in Q(p)\}\right)}$

How it is computed:

- EDT values, distances, and the radius are all physical, using the foreground affine's spacing. Rotated and anisotropic grids are handled.
- $\operatorname{comp}$ is the 26-connected foreground component, i.e. voxels touching by a face, edge, or corner are connected. A nearby vessel that does not touch is never searched.
- The EDT comes from the whole foreground; components only limit which voxels are searched.
- Every foreground voxel in the ball is searched, not only skeleton voxels.
- $D(p)$ always counts toward the maximum. This matters for graph nodes, whose $D(p)$ is interpolated at a fractional position.
- A voxel centre exactly on the sphere counts as inside, within a relative tolerance of $10^{-6}$. This absorbs the float32 precision of NIfTI affines.
- Graph nodes take their component from the foreground cell they sit in (the checker's rule). On a shared face, edge, or corner, all touching foreground cells are checked; a node with none, or with cells from different components, is rejected by node ID.
- The raw ratio is shown; it is not rescaled.

**Radius multiplier α**, beside Colour by:

- Range 1.0–3.0, default 1.5, step 0.1. Enabled only for Local EDT ratio.
- Hover or click the **?** icon for a reminder: search radius = α × EDT at that point, measured in physical units; only the same 26-connected component counts; larger α searches farther, may include wider neighbouring sections of the same component, and takes longer.

Reading the value:

- 1 means no larger EDT was found nearby. It does not prove the point is on the anatomically correct centreline.
- For skeleton voxels, $\frac{1}{1+\alpha} \le r(p) \le 1$: 0.5 at α = 1, 0.4 at α = 1.5, 0.25 at α = 3. The EDT changes by at most the distance moved, so nothing inside the ball exceeds $(1+\alpha)\,D(p)$.
- Near the wall, values plateau near that lower bound, because the search radius shrinks with $D(p)$. A low value says "off-centre", not how far off-centre.
- Larger α never raises the ratio. It can reach into a wider neighbouring section or a junction of the same component and lower it.
- Graph nodes use interpolated $D(p)$, so the lower bound is not guaranteed for them (0.241 was observed at α = 3, just under 0.25).

Warnings (status tooltip, run log, and the selected sample's details):

- **Search ball reaches beyond the image**: the ball crosses the voxel-centre domain $[0, n-1]$ on some axis. Only observed voxels are searched, so a larger EDT outside the image could be missed. The check is purely geometric; it also fires where the foreground does not reach that border.
- **Limited neighbourhood support**: no other same-component voxel centre lies in the ball, so the maximum rests on $D(p)$ alone and the ratio is 1 by definition.
- The calculation runs on the foreground bounding box plus one background voxel. That crop holds every foreground voxel, so it never drops candidates, and it does not trigger the border warning.

Display:

- Fixed 0–1 legend titled "Local EDT ratio", with no unit. NIfTI bands split 0–1 into equal ranges; GraphML nodes use the continuous gradient; edges stay grey. Equal values keep the 0–1 scale.
- Clicking a sample shows the ratio, Voxel EDT and local maximum EDT (physical units), α and the search radius, voxel and physical position, node ID for GraphML, and any sample warnings.
- **Distance method** is locked to Voxel EDT while Local EDT ratio is selected. The last distance method returns when you switch back to Distance.
- A centeredness measure based on Surface distance is not available yet.

### Inputs and output

- Foreground: binary NIfTI (`.nii` / `.nii.gz`).
- Skeleton: binary NIfTI, or GraphML with node `voxel_pos`. Edges must have `centerline_voxel_points`.
- GraphML files that also store a node attribute named `id` (for example laplskel output) are fine: that attribute names the nodes, as in `skelhub graphviz`.
- **Calculate** runs loading, checks, and the calculation in the background with the selected settings. Progress shows the loading stages and the local EDT ratio's sample batches; the EDT, component labelling, surface reconstruction, and distance queries have no percentage.
- NIfTI: one block per skeleton voxel, drawn at its physical size and orientation, coloured in discrete bands.
- GraphML: nodes coloured on a continuous gradient. Edges follow `centerline_voxel_points` and are always neutral grey; they draw the shape only and carry no distance samples.

### Controls

- Color preset: Viridis, Plasma, Inferno, Cividis.
- Color bands (2–16, NIfTI only): equal-width value ranges between the smallest and largest sample. If all samples are equal, one colour is used.
- Node size and edge thickness (GraphML only). NIfTI blocks keep their physical voxel size.
- **Reset / Fit view**. Drag rotates, Shift+drag pans, wheel or right-drag zooms.
- Click a voxel or node to see its value, voxel position, and physical position, plus the node ID for GraphML. Dragging does not select.
- The legend title, selection details, status, and run log all describe the *displayed* result ("Voxel EDT (mm)", "Surface distance (mm)", or "Local EDT ratio" with its α). The unit comes from the foreground header (mm, µm, m). If the header has no unit, the label says "unit unspecified"; it never assumes mm. The ratio itself has no unit.
- The side panel collapses with **Controls ▸**.

Recalculation and caching:

- Colour and size changes reuse the calculated samples and keep the camera.
- Changing Colour by, the method, or α does not clear the view. The status turns amber ("Showing … · … not yet applied") until you press Calculate. While a calculation runs, the status still names the displayed result.
- Recalculating the same file pair with other settings keeps the camera, the appearance settings, and the selected sample.
- Results are cached per file pair and settings (metric, method, and α with connectivity for the ratio), so returning to already-calculated settings is instant. α does not affect distance results or their cache.
- If the settings change while a calculation runs, its result is cached but not shown.
- Changing either input clears the view and the cache.

### Checks before calculation

A failed check shows a warning, and nothing is drawn. Nothing is silently projected, resampled, or switched to the other method.

All settings:

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

Local EDT ratio adds:

- α is a finite number between 1.0 and 3.0.
- The distance method is Voxel EDT; Local EDT ratio with Surface distance is rejected.
- Every sample has a positive, finite EDT.
- Every graph node belongs to exactly one foreground component (see above).

Where the foreground reaches the image border (Surface distance):

- The calculation runs.
- The surface is left open there, and a warning in the status and run log says distances are measured to the observed surface only; an unobserved boundary beyond the image could be closer.
- Inside/outside is decided with a separate, closed copy of the surface (the image padded with background). That copy matches the open surface within the voxel-centre hull. Its caps lie outside the hull and never contribute to a distance.

### Limitations

- The checks show that both files fit the same grid. They cannot prove the files came from the same source data.
- Interpolated Voxel EDT values estimate the distance between voxel centres; they are not distances to a surface.
- Surface distance follows the staircase-like marching-cubes surface of the voxel mask, and marching cubes resolves ambiguous diagonal contacts by its own rule. Nodes exactly at such contacts may be rejected as outside.
- Surface distance currently supports GraphML only.
- The local EDT ratio is a local check only. It cannot tell a well-centred skeleton from one that runs down the middle of the wrong structure, and a high value does not validate anatomy.
- The local EDT ratio searches point by point. On a 480 × 380 × 270 ex vivo foreground with 178,687 skeleton voxels it added about 4–4.5 s to the 5.4 s distance run, almost independent of α. The full EDT and label volumes exist only during a calculation.
- Distance queries run node by node. Very large graphs (hundreds of thousands of nodes) take noticeably longer.
- Only the sampled values are cached; the full EDT volume is not kept. Only the most recent foreground surface is kept.
- Large skeleton NIfTI files draw many instanced blocks, and there is no voxel-count warning yet.
- Without a working OpenGL display, the tab explains why the viewer is unavailable.
