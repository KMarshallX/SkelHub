# AGENT.md — Curve Skeletonization for NIfTI Volumes

## Project Goal

Implement the curve skeletonization algorithm described in:

> Jin et al., "A robust and efficient curve skeletonization algorithm for tree-like objects using minimum cost paths," *Pattern Recognition Letters* 76 (2016) 32–40.

The program accepts a NIfTI file as input and outputs the computed curve skeleton as a NIfTI file. It is designed for 3D tree-like fuzzy objects such as airways or vascular trees.

---

## Target File Structure

```
skeletonize/
├── AGENT.md                  # This file
├── README.md                 # User-facing usage instructions
├── requirements.txt          # Python dependencies
├── main.py                   # CLI entry point
│
├── io/
│   ├── __init__.py
│   ├── nifti_reader.py       # Load NIfTI → numpy array + affine
│   └── nifti_writer.py       # Save numpy array → NIfTI file
│
├── core/
│   ├── __init__.py
│   ├── distance_transform.py # Fuzzy distance transform (FDT)
│   ├── maximal_balls.py      # Fuzzy center of maximal ball (fCMB) detection
│   ├── lsf.py                # Local significance factor (LSF)
│   ├── geodesic.py           # Geodesic distance computation over object voxels
│   ├── path_cost.py          # Step-cost and minimum cost path (MCP)
│   ├── dilation.py           # Local scale-adaptive dilation
│   └── skeleton.py           # Single-object skeleton growth loop
│
├── utils/
│   ├── __init__.py
│   ├── connected_components.py  # Label disconnected sub-trees within one object
│   ├── multi_object.py          # Decompose volume into objects; run skeleton per object; merge results
│   └── root_detection.py        # Automatic root voxel selection (per object)
│
└── tests/
    ├── __init__.py
    ├── test_distance_transform.py
    ├── test_maximal_balls.py
    ├── test_lsf.py
    ├── test_path_cost.py
    ├── test_skeleton.py
    ├── test_multi_object.py
    └── fixtures/
        ├── generate_fixtures.py  # Script to programmatically create all synthetic NIfTI fixtures
        ├── straight_tube.nii.gz  # Generated: single straight tube
        ├── y_tube.nii.gz         # Generated: Y-shaped branching tube
        ├── y_tube_noisy.nii.gz   # Generated: Y-tube with boundary noise protrusions
        └── two_tubes.nii.gz      # Generated: two disconnected tubes in one volume

```

---

## Algorithm Summary (for the agent)

The algorithm works as follows. Read this carefully before writing any code.

### Step 0 — Setup and Multi-Object Decomposition

- Load the NIfTI volume into a 3D numpy array with float membership values in [0, 1]. Binary inputs (0/1 integers) should be cast directly; grayscale inputs should be normalised.
- **Decompose the volume into individual objects** using `utils/multi_object.py` before any skeletonization begins. The input volume may contain multiple spatially disconnected tree-like structures (e.g. left and right lung airways, or multiple vessels). Each must be skeletonized independently. Use 26-connected component labelling to identify all distinct objects. Filter out components smaller than a minimum voxel count threshold (default: 50 voxels) to ignore noise specks.
- For **each object** independently:
  - Select a **root voxel** `o`. Default: the voxel with the highest FDT value (deepest interior point). An alternative is the most interior point along the topmost slice, useful for airways.
  - Run the full skeleton algorithm (Steps 1–8) on that object's sub-volume.
- After all objects are processed, **merge all per-object skeletons** into a single output array with the same shape as the input. If `--label-objects` is set, each object's skeleton voxels are assigned its component label integer; otherwise all skeleton voxels are set to 1.

### Step 1 — Fuzzy Distance Transform (FDT)

File: `core/distance_transform.py`

The FDT generalises Euclidean distance transform to fuzzy objects. For each object voxel `p` (where `μ_O(p) > 0`), `FDT(p)` is the minimum weighted path length to the object boundary. For binary inputs this reduces to the standard Euclidean DT.

Use `scipy.ndimage.distance_transform_edt` for binary objects as a first-pass approximation. For proper fuzzy support, implement iterative propagation using the formula in the paper (Eq. 1). This module must expose:

```python
def compute_fdt(volume: np.ndarray) -> np.ndarray:
    """Returns FDT array, same shape as volume. Zero outside object support."""
```

### Step 2 — Fuzzy Centers of Maximal Balls (fCMB)

File: `core/maximal_balls.py`

A voxel `p` is an fCMB if for **every** 26-neighbour `q`:

```
FDT(q) - FDT(p) < 0.5 * (μ_O(p) + μ_O(q)) * |p - q|
```

where `|p - q|` is the Euclidean distance between voxels (1 for face-adjacent, √2 for edge-adjacent, √3 for corner-adjacent).

This module must expose:

```python
def compute_fcmb_mask(volume: np.ndarray, fdt: np.ndarray) -> np.ndarray:
    """Returns boolean mask, True where voxel is an fCMB."""
```

### Step 3 — Local Significance Factor (LSF)

File: `core/lsf.py`

For each object voxel `p`, LSF measures the collision impact of independent fire-fronts:

```
LSF(p) = 1 - f_+(  max_{q ∈ N*(p)}  [ (FDT(q) - FDT(p)) / (0.5*(μ(p)+μ(q))*|p-q|) ]  )
```

where `f_+(x) = x if x > 0 else 0` and `N*(p)` is the 26-neighbourhood of `p` excluding `p` itself.

- LSF is in (0, 1] at fCMB voxels; it is 0 at non-fCMB voxels.
- A **strong quench voxel** is an fCMB with `LSF > 0.5`.

```python
def compute_lsf(volume: np.ndarray, fdt: np.ndarray) -> np.ndarray:
    """Returns LSF array, same shape as volume. Zero at non-fCMB voxels."""
```

### Step 4 — Geodesic Distance

File: `core/geodesic.py`

Given the current marked volume `O_marked` and the set of strong quench voxels `C_O`, compute the geodesic distance of each voxel in `C_O` from `O_marked`. Geodesic paths are confined to the object support `O`.

Use a priority queue (min-heap / Dijkstra) over the object voxels. Edge weights are the Euclidean distances `|p - q|` (not the path-cost weights — geodesic distance is purely geometric).

```python
def compute_geodesic_distance(
    object_mask: np.ndarray,      # boolean, True = object voxel
    source_mask: np.ndarray,      # boolean, True = already-marked voxels
) -> np.ndarray:
    """Returns geodesic distance from source for every voxel in object_mask.
    Voxels outside object_mask have value np.inf."""
```

### Step 5 — Minimum Cost Path

File: `core/path_cost.py`

The step-cost between two 26-adjacent voxels `p` and `q` is:

```
SC(p, q) = |p - q| / (ε + average(LSF(p) + LSF(q)))^2
```

where `ε = 0.01` (constant).

The total cost of a path is the sum of step-costs. Use Dijkstra's algorithm (via a min-heap) to find the minimum cost path from a target quench voxel `v_i` back to the current skeleton `S`.

```python
def minimum_cost_path(
    object_mask: np.ndarray,
    lsf: np.ndarray,
    source_coords: list[tuple],   # voxels in the current skeleton S
    target_coord: tuple,          # the farthest quench voxel v_i
    epsilon: float = 0.01,
) -> list[tuple]:
    """Returns ordered list of voxel coordinates forming the minimum cost path."""
```

### Step 6 — Local Scale-Adaptive Dilation

File: `core/dilation.py`

After a new branch `B_i` is found, mark the object volume it represents. At each voxel `p` on `B_i`, the dilation radius is `2 * FDT(p)`. This is computed with a distance-propagation approach:

- Initialise `DS(p) = scale(p) = 2 * FDT(p)` for `p ∈ B_i`.
- Initialise `DS(p) = -inf` for all other object voxels.
- Iteratively update: `DS(p) = max_{q ∈ N*(p)} DS(q) - |p - q|` until convergence.
- Mark all voxels where `DS(p) >= 0` as part of the dilated volume.

```python
def local_scale_adaptive_dilation(
    object_mask: np.ndarray,
    branch_coords: list[tuple],
    fdt: np.ndarray,
) -> np.ndarray:
    """Returns boolean mask of voxels covered by this branch's dilation."""
```

### Step 7 — Branch Significance

File: `core/skeleton.py` (inline helper)

The significance of a candidate branch `B_i` (only the portion outside `O_marked`) is:

```
significance(B_i) = sum of LSF(p) for p in B_i and p not in O_marked
```

The significance threshold at the junction point `p_v` (where `B_i` meets the current skeleton) is:

```
threshold = 3 + 0.5 * FDT(p_v)
```

A branch is accepted only if `significance(B_i) >= threshold`.

### Step 8 — Main Skeleton Loop

File: `core/skeleton.py`

```
initialise skeleton S = {root voxel o}
initialise O_marked = dilation around o

while True:
    find disconnected sub-trees T_1, T_2, ... in (O - O_marked)
    if no sub-trees: break

    found_any = False
    for each sub-tree T_i:
        C_i = strong quench voxels in T_i
        if C_i is empty: continue

        compute geodesic distance from O_marked for all voxels in C_i
        v_i = argmax geodesic distance (the farthest strong quench voxel)

        compute minimum cost path B_i from v_i to S
        compute significance of B_i
        if significance(B_i) < threshold: continue

        add B_i to S
        dilate B_i → D_i
        O_marked = O_marked ∪ D_i
        found_any = True

    if not found_any: break

return S
```

Key insight: all sub-tree branches are computed **in the same iteration** (they are independent), which gives O(log N) average complexity instead of O(N).

---

## Milestones

Work through these in order. Do not start a milestone until all tests for the previous one pass.

---

### Milestone 1 — Project Scaffold and I/O

**Goal:** Runnable CLI that loads a NIfTI file and saves it back unchanged.

Tasks:
1. Create the full directory structure listed above.
2. Implement `io/nifti_reader.py`:
   - Use `nibabel` to load `.nii` or `.nii.gz` files.
   - Return `(data: np.ndarray, affine: np.ndarray, header)`.
   - Normalise to float32 in [0, 1] if the input is not already binary/float.
3. Implement `io/nifti_writer.py`:
   - Accept `(data, affine, header, output_path)`.
   - Save as `.nii.gz` by default.
4. Implement `main.py` CLI using `argparse`:
   - `--input` / `-i`: path to input NIfTI
   - `--output` / `-o`: path for output skeleton NIfTI
   - `--root-method`: `"max_fdt"` (default) or `"topmost"`
   - `--threshold-scale`: float multiplier for the significance threshold (default 1.0)
   - `--min-object-size`: minimum voxel count for a component to be skeletonized (default 50)
   - `--label-objects`: flag; if set, output skeleton voxels are labelled by component index instead of all being 1
5. Write `requirements.txt`:
   ```
   nibabel>=5.0
   numpy>=1.24
   scipy>=1.10
   scikit-image>=0.21
   ```
6. Write `README.md` with installation and usage instructions.
7. Implement `utils/multi_object.py`:
   - `decompose(volume, min_size)` — returns a list of `(component_label, sub_mask)` tuples, one per object passing the size filter, using 26-connected labelling via `scipy.ndimage.label`.
   - `merge_skeletons(shape, results)` — accepts a list of `(label, skeleton_mask)` tuples and combines them into one output array.
8. Implement `tests/fixtures/generate_fixtures.py`:
   - Must be runnable as a standalone script: `python tests/fixtures/generate_fixtures.py`
   - Generates and saves all synthetic NIfTI fixtures listed in the file structure using numpy and nibabel. No real data required.
   - **`straight_tube.nii.gz`**: a 20×20×60 binary volume with a single cylindrical tube of radius 3 along the Z axis.
   - **`y_tube.nii.gz`**: a 40×40×60 binary volume with a trunk (radius 3, Z=0–30) that splits into two branches at Z=30 (branch 1: +X direction, branch 2: +Y direction, each length 20, radius 2).
   - **`y_tube_noisy.nii.gz`**: same as `y_tube` but with small random spherical protrusions (radius 1–2 voxels) added to 1% of boundary voxels.
   - **`two_tubes.nii.gz`**: a 60×20×60 binary volume containing two spatially disconnected straight tubes (same geometry as `straight_tube`), separated by at least 10 voxels of background.

**Acceptance test:** `python main.py -i input.nii.gz -o out.nii.gz` runs without error and produces an output file. `python tests/fixtures/generate_fixtures.py` runs without error and all four fixture files are created.

---

### Milestone 2 — FDT and fCMB

**Goal:** Correct computation of the fuzzy distance transform and centers of maximal balls.

Tasks:
1. Implement `core/distance_transform.py` — `compute_fdt()`.
   - For binary inputs: use `scipy.ndimage.distance_transform_edt`.
   - For fuzzy inputs: implement the iterative fuzzy propagation scheme (optional extension; binary DT is sufficient for Milestone 2).
2. Implement `core/maximal_balls.py` — `compute_fcmb_mask()`.
   - Iterate over all 26-neighbours using pre-computed offset arrays for speed.
   - Vectorise with numpy where possible; avoid Python loops over all voxels.
3. Write unit tests in `tests/test_distance_transform.py` and `tests/test_maximal_balls.py`.
   - Use the fixtures generated by `generate_fixtures.py` (`straight_tube.nii.gz`).
   - Assert that FDT peaks at the centreline.
   - Assert that fCMBs lie along the centreline.

**Acceptance test:** All tests pass. FDT and fCMB visualised on a synthetic tube look correct.

---

### Milestone 3 — LSF and Geodesic Distance

**Goal:** Correct LSF computation and geodesic distance over the object.

Tasks:
1. Implement `core/lsf.py` — `compute_lsf()`.
   - Re-use the neighbour offset arrays from Milestone 2.
   - Strong quench voxels (`LSF > 0.5`) should cluster along the centreline.
2. Implement `core/geodesic.py` — `compute_geodesic_distance()`.
   - Use `heapq`-based Dijkstra over the 26-connected object graph.
   - Edge weight = Euclidean distance between adjacent voxels.
3. Write tests for both modules.

**Acceptance test:** On the synthetic tube fixture, the strong quench voxels tile the centreline and geodesic distance increases monotonically from the source end.

---

### Milestone 4 — Minimum Cost Path

**Goal:** Correct minimum cost path between a target voxel and the current skeleton.

Tasks:
1. Implement `core/path_cost.py` — `minimum_cost_path()`.
   - Use Dijkstra with step-cost `SC(p, q) = |p-q| / (ε + avg(LSF(p), LSF(q)))^2`.
   - Return the ordered list of voxels forming the path.
2. Verify on a synthetic shape with a known centreline that the path follows it, including around sharp corners (reproduce the intuition of Fig. 3 from the paper in a simple 2D cross-section test).
3. Write tests in `tests/test_path_cost.py`.

**Acceptance test:** Minimum cost path on the synthetic tube returns voxels that are within 1 voxel of the geometric centreline.

---

### Milestone 5 — Dilation and Branch Significance

**Goal:** Correct volume marking after each branch is added.

Tasks:
1. Implement `core/dilation.py` — `local_scale_adaptive_dilation()`.
   - Implement the iterative distance propagation described in Section 2.3.
   - Stop when `DS` no longer changes (use a convergence tolerance of 1e-6).
   - Optimise: use a priority queue or wavefront approach if the naive iteration is too slow.
2. Add `significance()` helper in `core/skeleton.py`.
3. Write tests in `tests/test_skeleton.py`:
   - Verify that the dilated volume around a branch covers the expected cross-section of the synthetic tube.
   - Verify significance correctly sums LSF outside the marked region.

**Acceptance test:** Dilation around the centreline of the synthetic tube covers ≈ the full tube cross-section.

---

### Milestone 6 — Full Skeleton Algorithm

**Goal:** End-to-end working skeleton extraction, including multi-object inputs.

Tasks:
1. Implement `utils/connected_components.py`:
   - Label 26-connected components of a binary mask using `scipy.ndimage.label` with a full 3×3×3 structuring element.
   - This is used *within* a single object's skeleton loop to find disconnected sub-trees at each iteration. It is distinct from the top-level multi-object decomposition in `utils/multi_object.py`.
2. Implement `utils/root_detection.py`:
   - `max_fdt`: return the voxel with the highest FDT value.
   - `topmost`: return the fCMB with the highest FDT value among those in the slice with the smallest Z-index (useful for airways).
   - Both functions operate on a single object's sub-mask, not the full volume.
3. Complete `core/skeleton.py` — implement the full single-object loop from Step 8.
4. Wire everything together in `main.py` via `utils/multi_object.py`:
   - Decompose the input into objects.
   - For each object, run `core/skeleton.py`.
   - Merge all results and save.
5. Write end-to-end tests in `tests/test_skeleton.py`:
   - Using `y_tube.nii.gz`: assert the output skeleton has exactly 3 branches and 0 false branches.
   - Using `y_tube_noisy.nii.gz`: assert still 3 branches and 0 false branches despite boundary noise.
6. Write multi-object tests in `tests/test_multi_object.py`:
   - Using `two_tubes.nii.gz`: assert the output contains skeletons for both tubes, with no voxels from one tube's skeleton appearing inside the other tube's volume.

**Acceptance test (synthetic):** The above pytest tests all pass.

**Acceptance test (real data):** Place the user-provided volume at `./test_data/smaller_patch_160/CLIP_MASKED_sub_160um_seg.nii.gz` and run:
```
mkdir -p ./test_outputs
python main.py -i ./test_data/smaller_patch_160/CLIP_MASKED_sub_160um_seg.nii.gz -o ./test_outputs/skel_m6.nii.gz --verbose
```
The program must complete without error and the `--verbose` log must report at least 1 object found and at least 1 skeletal branch detected.

---

### Milestone 7 — Performance and Validation

**Goal:** Fast enough to run on real MRI/CT data; validated on a user-provided volume.

Tasks:
1. Profile each module and identify bottlenecks. Typical hotspots:
   - The Dijkstra loops (use numpy-vectorised neighbour expansion or `scipy.sparse.csgraph.shortest_path` on a pre-built graph for small volumes).
   - The iterative dilation (replace Python while-loop with scipy morphology if convergence is slow).
2. Add a `--verbose` flag to `main.py` that logs, per object: iteration count, branches added per iteration, and wall-clock time.
3. Add a `--max-iterations` safety cap (default 100) to prevent infinite loops on pathological inputs.

**Acceptance test (synthetic data):** Place the user-provided MRI volume at `./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_11.nii`, `./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_12.nii`, `./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_13.nii` and run respectively:
```
python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_11.nii -o ./test_outputs/skel_m7_synthetic_11.nii.gz --verbose

python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_12.nii -o ./test_outputs/skel_m7_synthetic_12.nii.gz --verbose

python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_13.nii -o ./test_outputs/skel_m7_synthetic_13.nii.gz --verbose
```

**Acceptance test (real data):** Place the user-provided MRI volume at `./test_data/bigger_patch/bigCLIP_MASKED_sub_160um_seg.nii.gz` and run:
```
python main.py -i ./test_data/bigger_patch/bigCLIP_MASKED_sub_160um_seg.nii.gz -o ./test_outputs/skel_m7.nii.gz --verbose
```
The program must complete without error. The `--verbose` output must show that the average number of iterations per object is in the range `[log2(N), sqrt(N)]` where N is the number of terminal branches detected, consistent with the computational complexity described in the paper.

---

## Coding Conventions

- All core functions must be **pure functions** (no side effects, no global state). This makes them easy to test and reason about.
- Every function must have a **docstring** explaining inputs, outputs, and units (voxels vs mm).
- Use `numpy` arrays throughout. Avoid Python loops over individual voxels — use vectorised operations and/or `scipy` spatial functions wherever possible.
- Coordinate convention: `(z, y, x)` index order to match numpy's default for NIfTI data loaded with nibabel (axis 0 = z/slice axis).
- All neighbour offsets for 26-connectivity should be pre-computed once as a module-level constant array of shape (26, 3).
- Use `np.float32` for FDT, LSF, and geodesic arrays to keep memory usage manageable for large CT volumes.

---

## Key Constants (from the paper)

| Symbol | Value | Location |
|--------|-------|----------|
| ε (epsilon) | 0.01 | `core/path_cost.py` |
| Strong quench threshold | LSF > 0.5 | `core/lsf.py` |
| Significance threshold | 3 + 0.5 × FDT(p_v) | `core/skeleton.py` |
| Dilation radius at p | 2 × FDT(p) | `core/dilation.py` |
| 26-neighbourhood | All offsets with max(|Δ|) = 1 | module-level constant |

---

## Dependencies

```
nibabel>=5.0        # NIfTI I/O
numpy>=1.24         # Array operations
scipy>=1.10         # Distance transform, connected components, sparse graphs
scikit-image>=0.21  # Optional: morphological helpers
```

---

## References

- Jin et al. (2016), Pattern Recognition Letters 76, pp. 32–40.
- Blum (1967) — grassfire transform.
- Sanniti di Baja (1994) — centers of maximal balls.
- Saha & Wehrli (2002) — fuzzy distance transform.