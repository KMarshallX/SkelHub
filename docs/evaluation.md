# Evaluation

SkelHub evaluation is algorithm-agnostic. It compares a predicted skeleton with a reference skeleton on the same voxel grid and reports these groups of measurements separately:

1. **Geometry coverage**: precision, recall and F1 at each requested tolerance.
2. **Geometry displacement**: how far apart the two skeletons are, in µm.
3. **Foreground EDT-sum agreement** (optional, needs a foreground mask): summed foreground clearance at each skeleton's voxels.
4. **Topology**: components, cycles and cavities (voxel Betti numbers).
5. **Endpoint diagnostics**: endpoint counts.

There is no combined score and no pass/fail verdict. For Python usage, see [API](API.md). For result fields, see [Structured Output](StructuredOutput.md).

The voxel evaluation that came before (schema v1: `Cp`, `Cr`, `OCC`, `BCC`, `E`, `P`) is kept [below](#legacy-v1-evaluation--historical-reference) for reference only. It is no longer run.

## Input scope

- Paired 3D binary skeleton volumes, values in $\{0, 1\}$.
- Optionally, one binary foreground mask shared by both skeletons, on the same grid.
- `.nii` / `.nii.gz` files, in-memory NumPy arrays, or a backend `SkeletonResult`.
- GraphML input is not supported yet.
- SkelHub does not register, resample, thin, prune or repair inputs.

## Usage

CLI:

```bash
skelhub evaluate \
  --pred prediction_skeleton.nii.gz \
  --ref reference_skeleton.nii.gz \
  --buffer-radius 50 100 \
  --buffer-radius-unit um \
  --foreground foreground_mask.nii.gz \
  --json-output report.json
```

- `-b/--buffer-radius` is required and takes one or more values. The first value is the **primary** tolerance; the others are reported separately. There is no default tolerance.
- `--buffer-radius-unit` is `voxels` (default) or `um`.
- `--foreground` (optional) adds the [foreground EDT-sum agreement](#foreground-edt-sum-agreement).
- `--pred-spatial-unit` / `--ref-spatial-unit` / `--foreground-spatial-unit` (`cm`, `mm`, `um`, `nm`) label a header whose unit is `unknown`. See [Unknown header units](#unknown-header-units). `--foreground-spatial-unit` without `--foreground` is rejected.
- `-v/--verbose` adds spatial-unit provenance, supporting counts, directional distances, Hausdorff distance and the Euler characteristic.

Python:

```python
from skelhub.api import evaluate_prediction_path
from skelhub.evaluation import evaluate_skeleton_volumes, evaluate_skeleton_result

# Files: units and affines come from each header.
result = evaluate_prediction_path("pred.nii.gz", "ref.nii.gz", buffer_radius=[50, 100], buffer_radius_unit="um")
print(result.status, result.geometry.primary.f1, result.geometry.distances.symmetric_p95_um)
print(result.topology.comparison(1))          # cycles: reference, prediction, difference, error

# Arrays: both arrays share one grid (see "Coordinates and units").
result = evaluate_skeleton_volumes(pred, ref, spacing=(0.05, 0.05, 0.05), spacing_unit="mm", buffer_radius=50, buffer_radius_unit="um")

# Backend output: `input_volume` is the VolumeData the backend ran on; it defines the prediction grid.
result = evaluate_skeleton_result(skeleton_result, reference_volume, input_volume=volume, buffer_radius=[1, 2])

# Optional foreground mask, one keyword per entry point:
#   files: foreground_path=..., foreground_spatial_unit=...   arrays: foreground_mask=<array on the same grid>
#   SkeletonResult: foreground=<VolumeData>, foreground_spatial_unit=...
print(result.foreground_edt)                  # None when no mask was supplied
```

`buffer_radius` takes a single number or a sequence; both go through the same code path. All three entry points share the same metric code and give identical results for identical inputs.

## Coordinates and units

Validation runs before any metric is computed. Invalid input raises a clear error instead of producing a score.

- **Binary 3D arrays** of matching shape.
- **Known spatial units**: NIfTI headers in metres, mm or micrometres (`micron`, treated as `um`). A header that says `unknown` needs a declared unit (below); without one it is rejected. Units are never guessed from coordinate sizes.
- **Unit factors to µm**: cm = 10,000; mm = 1,000; um = 1; nm = 0.001; metre (header or legacy Python spelling) = 1,000,000. All spacing and the full affine, translation included, are converted to µm.
- **Same physical grid**: both full voxel-to-world affines (spacing, orientation and origin) are converted to µm and must agree. The tolerance is $10^{-3}$ of the smallest voxel spacing. Equivalent grids written in different units, such as 0.05 mm and 50 µm, are accepted. An origin shift, a flipped axis or a unit mismatch is rejected.
- **Orthogonal grids only**: anisotropic spacing and rotated or permuted axes are supported. Sheared affines are rejected, because distances use per-axis spacing, which is exact only on orthogonal grids.
- **Consistent headers**: NIfTI `pixdim` spacing must match the affine column lengths within a relative error of $10^{-5}$.
- **In-memory arrays** (same-grid contract): both arrays (and `foreground_mask`) use one transform, either $\mathrm{diag}(\text{spacing})$ or an explicit `affine` whose column lengths equal `spacing`, expressed in `spacing_unit`.
- **`SkeletonResult`**: the prediction takes its affine and header units from `input_volume`, and its shape must match. Both `VolumeData` objects need header units or a declared unit.

### Unknown header units

Some NIfTI files store spacing and affine values without saying which unit they use (header unit `unknown`). You can declare that unit for each input, as `cm`, `mm`, `um` or `nm`:

```bash
skelhub evaluate --pred pred.nii.gz --ref ref.nii.gz \
  --pred-spatial-unit mm --ref-spatial-unit mm \
  --buffer-radius 50 --buffer-radius-unit um
```

In Python, use `pred_spatial_unit=` / `ref_spatial_unit=` / `foreground_spatial_unit=` on `evaluate_prediction_path`, `evaluate_skeleton_files` and `evaluate_skeleton_result`. For `evaluate_skeleton_result`, they apply to `input_volume`, `reference` and `foreground`. A `VolumeData` without a header counts as `unknown`. The array evaluator requires `spacing_unit`. Python also accepts the legacy spellings `meter` and `micron` (= `um`); the CLI does not.

| Header unit | Declared unit                    | Result                                     |
| ----------- | -------------------------------- | ------------------------------------------ |
| known       | none                             | header unit used                           |
| known       | equivalent (`micron` = `um`)     | accepted; the header stays the source      |
| known       | different                        | rejected; a known unit is never overridden |
| `unknown` | supported                        | declared unit used, with a warning         |
| `unknown` | none                             | rejected, with instructions                |
| unsupported | any                              | rejected                                   |

- **A declaration labels the stored numbers; it does not change them.** Stored spacing 0.05 declared `mm` gives 50 µm. Stored spacing 1 declared `um` gives 1 µm, not 50 µm. The same factor converts the header spacing, the affine's linear part and its translation.
- Each input is resolved on its own. A unit is never borrowed from the other file, the file name, the spacing values or the tolerance.
- The input files and in-memory headers, affines and arrays are not modified.
- All other checks still apply after the unit is resolved. Shape mismatches are reported before missing units. Affine mismatches, shear, header/affine disagreement and non-binary data are still rejected.
- `cm` and `nm` exist only as declarations. SkelHub never writes unit codes into NIfTI headers.
- **Provenance:** every declared unit adds a warning, shown in the normal terminal report and kept in `EvaluationResult.warnings` and the JSON. It names the input, says the header unit was unknown, and gives the effective unit and the resulting spacing in µm. `metadata` records `source_spatial_units` (what the header said: `null` for arrays), `effective_spatial_units` (canonical: `meter`, `cm`, `mm`, `um` or `nm`) and `spatial_unit_sources` (`header` or `user`). The mask's units are recorded in `foreground_edt_agreement.mask`.

## Tolerances

- Every tolerance is a maximum Euclidean distance between voxel centres, in µm. It applies to coverage only. It never changes topology or endpoints.
- Values must be finite, $\ge 0$ and distinct. $\tau = 0$ means exact voxel-centre matching.
- `um` values are used as given.
- `voxels` values are multiplied by the voxel spacing, and only on **isotropic** grids. On anisotropic grids a voxel radius has no single physical size, so it is rejected; give the tolerance in µm instead.
- The test $d \le \tau$ allows a relative slack of $10^{-5}$. This absorbs float32 header rounding: 0.05 mm is stored as 0.0500000007 mm, and without the slack a 50 µm tolerance would miss axial neighbours.
- Each tolerance is reported separately. Results are never averaged across tolerances.

## Geometry

Let $S_p$ and $S_r$ be the prediction and reference foreground voxel centres. Let $d(x, S) = \min_{y \in S} \lVert x - y \rVert_2$ in µm. The two directional distance collections are computed once:

$$
D_{p\to r} = \{ d(p, S_r) : p \in S_p \}, \qquad D_{r\to p} = \{ d(r, S_p) : r \in S_r \}.
$$

Implementation: an exact Euclidean distance transform with the physical spacing (`scipy.ndimage.distance_transform_edt`). It runs on the bounding box of both skeletons, which contains every nearest neighbour, so cropping changes no distance. Each distance field is then sampled at the other skeleton.

### Coverage (per tolerance $\tau$)

$$
\mathrm{Precision}_\tau = \frac{\sum_{p \in S_p} \mathbf{1}[d(p, S_r) \le \tau]}{|S_p|}, \qquad
\mathrm{Recall}_\tau = \frac{\sum_{r \in S_r} \mathbf{1}[d(r, S_p) \le \tau]}{|S_r|},
$$

$$
F1_\tau = \frac{2\,\mathrm{Precision}_\tau\,\mathrm{Recall}_\tau}{\mathrm{Precision}_\tau + \mathrm{Recall}_\tau}, \quad F1_\tau = 0 \text{ when both are } 0.
$$

Supporting counts are kept for each direction: matched and unmatched **prediction** voxels, and matched and unmatched **reference** voxels. No true-positive count is shared between the two directions, so extra prediction voxels near the reference cannot raise recall.

### Displacement (µm)

$$
\mu_{p\to r} = \frac{1}{|S_p|} \sum_{p \in S_p} d(p, S_r), \qquad
\mu_{r\to p} = \frac{1}{|S_r|} \sum_{r \in S_r} d(r, S_p),
$$

$$
D_{\mathrm{mean}} = \frac{\mu_{p\to r} + \mu_{r\to p}}{2}, \qquad
D_{95} = \max\big(Q_{0.95}(D_{p\to r}),\, Q_{0.95}(D_{r\to p})\big), \qquad
H = \max\big(\max D_{p\to r},\, \max D_{r\to p}\big).
$$

- Both directions get equal weight. The two collections are never pooled.
- $Q_{0.95}$ uses NumPy's default `linear` percentile interpolation.
- Main output: $D_{\mathrm{mean}}$ and $D_{95}$. Detailed output: directional means, P95s and maxima. Diagnostic: Hausdorff $H$, which exposes isolated outliers that $D_{95}$ can hide.

## Foreground EDT-sum agreement

Optional. It runs only when a foreground mask is supplied; otherwise it is reported as "Not computed—no foreground mask supplied" and every other metric is unchanged.

**Mask rules.** One binary 3D mask (values 0 and 1 only) shared by both skeletons. It must have the skeletons' shape and physical grid, and passes the same affine, orthogonality, header-spacing and unit checks. All-zero and all-one masks are rejected. An invalid mask rejects the whole evaluation. The mask is never resampled, registered, thresholded or thinned.

**Definition.** Let $F$ be the mask and $\mathrm{EDT}_F(x)$ the Euclidean distance, in µm, from voxel centre $x$ to the nearest background voxel centre of $F$ ($0$ for background voxels). One `scipy.ndimage.distance_transform_edt` runs on the **full** mask with physical spacing. For each skeleton $S \in \{S_p, S_r\}$:

$$
\Sigma(S) = \sum_{x \in S} \mathrm{EDT}_F(x), \qquad
\bar{e}(S) = \frac{\Sigma(S)}{|S|}, \qquad
o(S) = \frac{|\{x \in S : x \notin F\}|}{|S|},
$$

$$
\delta = \frac{\Sigma(S_p) - \Sigma(S_r)}{\Sigma(S_r)}, \qquad |\delta| = \frac{|\Sigma(S_p) - \Sigma(S_r)|}{\Sigma(S_r)}.
$$

- Skeleton voxels outside the mask sample $0$. They stay in the sum and in $|S|$, and each skeleton with any adds a warning.
- Sums use float64. Reported per skeleton: EDT sum, mean EDT, voxel count, outside-mask count and fraction. JSON stores $\delta$, $|\delta|$ and $o$ as fractions; reports show them as percentages.
- **Boundary policy**: only background observed inside the image counts. The mask is not padded or cropped. Cropping to the skeletons' bounding box would drop the background that sets the distances. When foreground touches an image face, a warning says clearance near that face may be overestimated.

| Case                   | Result                                                                    |
| ---------------------- | ------------------------------------------------------------------------- |
| No mask                | `foreground_edt_agreement` is `null`; reason "No foreground mask supplied" |
| Empty skeleton         | sum 0, voxels 0, outside 0; mean and outside fraction `null`, with a reason |
| $\Sigma(S_r) = 0$     | $\delta$ and $\lvert\delta\rvert$ `null`, with a reason                  |

Empty inputs keep their usual `status`.

**Interpretation.** $\delta < 0$: the prediction has less total clearance than the reference (fewer voxels, or voxels closer to the boundary); $\delta > 0$: more. Matching sums do **not** show spatial or topological agreement: voxel count and clearance can cancel out, so read $\delta$ next to coverage and topology. The sum depends on sampling, branch orientation and resolution. It is not a physical branch-length integral.

## Topology

Computed on each **original** skeleton, never on a tolerance buffer. Foreground uses 26-connectivity and background uses 6-connectivity.

1. Crop to the foreground bounding box and pad with one background layer. Everything outside the box is background joined to the exterior, so this changes nothing. The padding stops structures that touch the image border from creating false cavities.
2. $\beta_0$: the number of 26-connected foreground components.
3. $\beta_2$: the number of 6-connected background components minus the single exterior component, i.e. enclosed cavities.
4. $\chi$: the 3D Euler characteristic from `skimage.measure.euler_number(..., connectivity=3)`, which uses the same 26/6 convention.
5. Independent cycles: $\chi = \beta_0 - \beta_1 + \beta_2 \;\Rightarrow\; \beta_1 = \beta_0 + \beta_2 - \chi$.

Cavities are counted, not assumed absent. Cycles are not counted in a naive voxel-adjacency graph; a solid 2×2×2 block has $\beta_1 = 0$. A negative Betti number raises an error instead of being clipped.

For each $k \in \{0, 1, 2\}$ the report gives the reference and prediction counts, $\Delta\beta_k = \beta_k(S_p) - \beta_k(S_r)$ and $E_{\beta_k} = |\Delta\beta_k|$. The Euler characteristic is included as supporting information. **Betti-count agreement** is $A_\beta = \mathbf{1}[E_{\beta_0} = E_{\beta_1} = E_{\beta_2} = 0]$. It means the counts match. It does not mean the topology is preserved: equal counts do not show that the same branches are connected.

## Endpoint diagnostics

$$
N_{\mathrm{end}}(S) = \sum_{x \in S} \mathbf{1}[n_{26}(x, S) = 1],
$$

where $n_{26}$ counts foreground 26-neighbours, excluding the centre voxel. The report gives both counts, $\Delta N_{\mathrm{end}} = N_{\mathrm{end}}(S_p) - N_{\mathrm{end}}(S_r)$ and $E_{\mathrm{end}} = |\Delta N_{\mathrm{end}}|$. These are diagnostics, not a quality score.

## Empty inputs

These rules apply after normal validation. Topology and endpoint counts are always computed.

| `status`           | Coverage                | Distances               | Meaning                                 |
| -------------------- | ----------------------- | ----------------------- | --------------------------------------- |
| `ok`               | computed                | computed                | Both skeletons are nonempty.            |
| `empty_prediction` | 0 at every tolerance    | `null`, with a reason | The prediction failed.                  |
| `empty_reference`  | `null`, with a reason | `null`, with a reason | Unsuitable for reference-based scoring. |
| `both_empty`       | `null`, with a reason | `null`, with a reason | No geometry score is awarded.           |

Matching counts between two empty inputs do not override the status. JSON output never contains `NaN` or `Infinity`.

## Report structure

The terminal report shows the status; F1, precision and recall at the primary tolerance, then at each other tolerance; the symmetric mean and P95 distance; the foreground EDT-sum agreement (or "Not computed"); reference → prediction counts for components, cycles and cavities; Betti-count agreement; endpoint counts; and warnings.

JSON (`--json-output`, schema `2.1`):

```text
schema_version   "2.1"
status           ok | empty_prediction | empty_reference | both_empty
metadata         message, pred_path, ref_path, shape, spacing_um, affine_um,
                 source_spatial_units, effective_spatial_units, spatial_unit_sources
                 (each {prediction, reference}), pred_voxels, ref_voxels
config           buffer_radius_unit, requested_tolerances, tolerances_um, primary_tolerance_um,
                 connectivity, endpoint/distance/percentile definitions, numeric tolerances,
                 metric_definitions ("skelhub-voxel-v2")
geometry         primary_tolerance_um,
                 tolerances[]  (requested order: tolerance_um, requested_value, requested_unit,
                                is_primary, precision, recall, f1, matched/unmatched counts),
                 distances_um  (directional means/P95/max, symmetric_mean_um,
                                symmetric_p95_um, hausdorff_um) or null
topology         connectivity, reference/prediction {beta_0, beta_1, beta_2, euler_characteristic},
                 beta_0/beta_1/beta_2 {reference, prediction, signed_difference, absolute_error},
                 betti_count_agreement
endpoint_diagnostics  {reference, prediction, signed_difference, absolute_error}
foreground_edt_agreement  null without a mask, else:
                 definition ("skelhub-foreground-edt-sum-v1"), distance, boundary_policy,
                 mask {path, header_spatial_unit, effective_spatial_unit, spatial_unit_source,
                       foreground_voxels, touches_image_boundary},
                 reference / prediction {edt_sum_um, mean_edt_um, skeleton_voxels,
                                         outside_mask_voxels, outside_mask_fraction},
                 signed_relative_difference, absolute_relative_difference, warnings
warnings         list of strings
unavailable      field -> reason for every null, e.g. "geometry.distances",
                 "foreground_edt_agreement", "foreground_edt_agreement.prediction.mean_edt_um"
```

The schema version marks the report format. It is not a switch: SkelHub has no legacy mode. Schema 2.1 only adds `foreground_edt_agreement` (and its `unavailable` entries); every 2.0 field keeps its name and meaning, and `metric_definitions` stays `skelhub-voxel-v2`.

## Interpretation

- **Recall is low**: parts of the reference are missing. **Precision is low**: the prediction has extra or misplaced voxels.
- Compare tolerances: if F1 jumps between the primary and a looser tolerance, most voxels are close to the reference but not on it.
- A large $H$ with a small $D_{95}$ means a few isolated outliers.
- If geometry is good but $\beta_1$ differs, loops were broken or added. Tolerance-based coverage cannot see this (example: one voxel removed from a closed loop gives F1 = 1 at 50 µm, with $\beta_1$ going from 1 to 0).

## Current limitations

- GraphML evaluation is deferred.
- Dataset-level aggregation (including Macro-F1) is deferred; each run evaluates one pair.
- Endpoint and junction matching is deferred.
- Branch recovery and spurious-branch metrics are deferred.
- Path-connectivity comparison is deferred.
- Matched-branch length and tortuosity errors are deferred.
- Geometry metrics weight voxel centres, not continuous branch length. Diagonal runs have fewer voxels per µm than axial runs.
- A tolerance can hide short gaps and nearby duplicate voxels.
- Equal Betti counts do not prove structural correspondence: a missing loop can be offset by an extra one elsewhere.
- Endpoint counts are sensitive to digital geometry: small spurs, thick spots and staircase patterns change neighbour counts. Matching counts do not show that endpoints correspond.
- Coordinate restrictions: files with `unknown` units need `--pred-spatial-unit` / `--ref-spatial-unit` / `--foreground-spatial-unit`; sheared grids are rejected; voxel-unit tolerances need isotropic spacing; inputs must already share one grid.
- Distance transforms use $O(N)$ memory over the shared bounding box. A 300×300×150 pair peaks at roughly 0.65 GB.
- The foreground EDT runs on the **full** mask volume (it cannot be cropped). It adds about 50 bytes per voxel at peak: about 0.63 GB for 300×300×150. It runs after the geometry transforms are released.
- Foreground EDT values near an image face that the mask touches can be too large, because the background beyond the image is unknown.
- The EDT sum depends on sampling, orientation and resolution: the same vessel voxelized differently gives a different sum. It is not a branch-length integral.

## Legacy v1 evaluation — historical reference

> **Historical.** This section documents the v1 voxel evaluation as implemented in SkelHub **v0.6.0** (tag `v0.6.0`, commit `1efa8a4`). Current SkelHub does not run it; check out that tag to reproduce it. The limitations below describe v1, not v2. v2 fixes the coverage, distance, cycle, combined-score and alignment problems; the rest still apply and are listed under [Current limitations](#current-limitations). The example code uses the v0.6.0 API.

Status at v0.6.0:

- Implemented: voxel-based v1 evaluation suite under `skelhub.evaluation`
- Input support: paired `.nii` and `.nii.gz` binary skeleton volumes
- Scope: 3D only, raw binary skeleton input only, no graph metrics yet

CLI:

```bash
skelhub evaluate \
  --pred prediction_skeleton.nii.gz \
  --ref reference_skeleton.nii.gz \
  --buffer-radius 1 \
  --buffer-radius-unit voxels
```

The evaluator validates both inputs explicitly before computing any metrics. It fails hard when:

- shapes do not match
- spacing does not match
- either input is not binary

The evaluator does not silently resample or silently coerce invalid volumes.

Implemented v1 metrics from (Youssef et al. 2015):

- Geometry preservation using the buffer method:
  `TP`, `FP`, `FN`, completeness `Cp`, and correctness `Cr`
  - Completeness: `Cp = TP / (TP + FN)`
  - Correctness: `Cr = TP / (TP + FP)`
- Morphology quality in 3D:
  raw signed `OCC`, `BCC`, and endpoint difference `E`
  - For each count, the implementation uses `(prediction_count - reference_count) / reference_count`.
  - Positive values mean extra counts; negative values mean missing counts; zero is ideal for count agreement.
  - This sign is opposite to the cited paper and the earlier version of this documentation. No implementation change is implied.
  - If the reference count is zero, the implementation returns zero when both counts are zero, otherwise the count difference, and emits a warning.
- Clipped and normalized morphology quality values:
  `X_clip = clip(X, -5, 5)` and `X_norm = 1 - abs(X_clip) / 5` (ideal case x_norm=1)
- Global performance score:
  `P = mean(Cp, Cr, OCC_normalized, BCC_normalized, E_normalized)`
  - This normalization differs from Youssef et al. (2015). Although larger values are intended to indicate better performance, the counterexamples below show why `P` should not be used alone to rank methods.

Connectivity conventions:

- foreground object: 26-connectivity
- background: 6-connectivity
- endpoint: voxel degree 1 under the 26-neighborhood

Buffer radius support:

- `--buffer-radius-unit voxels` uses a voxel-distance structuring element
- `--buffer-radius-unit um` uses physical micrometers derived from the image spacing
- anisotropic spacing emits an explicit warning so users can double-check the chosen dilation radius and unit
- The radius is a maximum Euclidean distance from a skeleton voxel centre, not a permitted empty gap between vessel surfaces. It affects geometry matching only; it does not repair skeleton connectivity.
- At isotropic 50 µm spacing, radii of 50 and 100 µm correspond to one and two voxel spacings. A one-spacing radius includes axial neighbours but excludes diagonal neighbours at `sqrt(2) * 50` µm.

Output modes:

- terminal report always printed
- optional JSON report with separate `metadata`, `config`, `raw_metrics`, `normalized_metrics`, and `warnings`

### v1 limitations

- **Input scope:** 3D binary skeleton volumes only; no GraphML input or graph-based metrics. GraphML evaluation support is deferred by the user decision on 2026-10-01.
- **Framework interface:** no direct `SkeletonResult`-first public path yet; the evaluator currently accepts files or arrays.
- **Completeness mixes sampling populations:** `TP` counts prediction voxels within the reference buffer, whereas `FN` counts reference voxels outside the prediction buffer. Consequently, `Cp = TP / (TP + FN)` is not reference coverage and can increase when nearby duplicate prediction voxels are added.
- **Geometry is thresholded:** there are no mean or percentile distance measurements. Locations inside the buffer receive the same match status; short breaks and missing tips can be hidden by the tolerance. Voxel counts also weight discretization rather than physical centreline length.
- **Background components do not measure 3D vessel cycles:** `BCC` counts disconnected background regions. A vessel loop generally leaves the surrounding background connected, so opening the loop can leave `BCC` unchanged. No independent-cycle count (`beta_1`) is currently computed.
- **Counts do not establish structural correspondence:** equal component or endpoint counts can conceal missing structures balanced by extras elsewhere. There is no endpoint/junction matching, branch recovery, path-connectivity comparison, or matched-branch tortuosity error. Raw 26-neighbour endpoint degrees are sensitive to local voxel geometry.
- **The combined score can be misleading:** clipping and normalizing morphology differences with `1 - abs(X_clip) / 5` gives a score of 0.8 even for a relative count error of magnitude one. Averaging these terms into `P` can reward empty or structurally incorrect predictions. Reference counts of zero also switch the raw metric to a count difference, reducing comparability across cases.
- **Spatial alignment is incompletely validated:** matching shapes and numerical spacing do not establish a common physical frame. Affines are stored but not compared; spatial-unit equality is checked only for physical-radius mode. Origin/orientation mismatches can therefore pass validation. There is no explicit resampling/alignment path.
- **Metric interpretation needs care:** the morphology sign convention above now matches the code, correcting the earlier documentation mismatch. A zero signed count difference means count agreement, not correct structure. Empty-pair conventions and the legacy formulas must be recorded when comparing reports across future metric versions.

#### Reproduced counterexamples

These cases exercise the current implementation with binary arrays of shape `(25, 25, 25)` and spacing `(1, 1, 1)`. Radii below are in voxels; the score behaviour also applies to corresponding voxel-radius tests at 50 µm spacing. Values are rounded for display.

| Case                                                                            | Radius | Current result                                         | Limitation exposed                                                                   |
| ------------------------------------------------------------------------------- | -----: | ------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Predict the first 10 voxels of a 20-voxel straight line                         |      0 | `Cp=0.5`, `Cr=1`, `P=0.90`                       | Half the reference is missing, yet the combined score is high.                       |
| Same half-line prediction                                                       |      1 | `Cp=0.526316`; actual reference coverage is `0.55` | Completeness differs from directional reference coverage.                            |
| Add an adjacent parallel copy of those 10 prediction voxels                     |      1 | `Cp=0.689655`; reference coverage remains `0.55`   | Duplicate prediction voxels increase completeness without recovering more reference. |
| Empty prediction against the straight reference                                 |      1 | `Cp=Cr=0`, but `P=0.52`                            | The combined score gives substantial credit to an empty prediction.                  |
| Remove one voxel from a closed square loop embedded in 3D                       |      1 | `Cp=Cr=1`, `BCC=0`, `P=0.92`                     | Tolerance hides the gap; background components miss the destroyed cycle.             |
| Identical arrays and spacing, with an affine translated by 100 coordinate units |     — | Input-pair validation accepts the mismatch             | Affine alignment is not checked.                                                     |

To reconstruct the geometry examples with NumPy indexing:

```python
import numpy as np
from skelhub.evaluation import evaluate_skeleton_volumes

ref = np.zeros((25, 25, 25), dtype=bool)
ref[3:23, 12, 12] = True
half = np.zeros_like(ref)
half[3:13, 12, 12] = True
duplicate = half.copy()
duplicate[3:13, 13, 12] = True
empty = np.zeros_like(ref)

loop = np.zeros_like(ref)
loop[5:20, 5, 12] = loop[5:20, 19, 12] = True
loop[5, 5:20, 12] = loop[19, 5:20, 12] = True
broken = loop.copy()
broken[12, 5, 12] = False

result = evaluate_skeleton_volumes(
    broken, loop, spacing=(1, 1, 1), buffer_radius=1,
    buffer_radius_unit="voxels",
)
```

## Citations

```
R. Youssef, A. Ricordeau, S. Sevestre-Ghalila, and A. Benazza-Benyahya, “Evaluation Protocol of Skeletonization Applied to Grayscale Curvilinear Structures,” in 2015 International Conference on Digital Image Computing: Techniques and Applications (DICTA), Adelaide, Australia: IEEE, Nov. 2015, pp. 1–6. doi: 10.1109/DICTA.2015.7371256.
```
