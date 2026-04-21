# Evaluation

SkelHub evaluation is designed to be algorithm-agnostic. It should consume `SkeletonResult` outputs or standardized prediction files rather than backend internals.

Current status:

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
  - $ BCC = \frac{N_b BCC(S_*)−N_b BCC(S)}{N_b BCC(S_∗)}$
  - $OCC = \frac{N_b OCC(S_∗)−N_b OCC(S)}{N_b OCC(S_∗)}$
  - $E = \frac{Nb E(S∗)−Nb E(S)}{Nb E(S∗)}$
  - Ideal values for raw BCC, OCC and E should be 0
- Clipped and normalized morphology quality values:
  `X_clip = clip(X, -5, 5)` and `X_norm = 1 - abs(X_clip) / 5` (ideal case x_norm=1)
- Global performance score:
  `P = mean(Cp, Cr, OCC_normalized, BCC_normalized, E_normalized)`
  - NOTE: this is different compared to (Youssef 2015) since the normalization of values is different. However, the higher index still point to higher performance in this case

Connectivity conventions:

- foreground object: 26-connectivity
- background: 6-connectivity
- endpoint: voxel degree 1 under the 26-neighborhood

Buffer radius support:

- `--buffer-radius-unit voxels` uses a voxel-distance structuring element
- `--buffer-radius-unit um` uses physical micrometers derived from the image spacing
- anisotropic spacing emits an explicit warning so users can double-check the chosen dilation radius and unit

Output modes:

- terminal report always printed
- optional JSON report with separate `metadata`, `config`, `raw_metrics`, `normalized_metrics`, and `warnings`

Current limitations:

- 3D only
- voxel-based only
- raw binary skeleton input only
- no graph-based metrics
- no direct `SkeletonResult`-first public path yet, though the current array-level evaluator leaves a clean extension seam for that future step

## Citations

@inproceedings{youssef_evaluation_2015,
	address = {Adelaide, Australia},
	title = {Evaluation {Protocol} of {Skeletonization} {Applied} to {Grayscale} {Curvilinear} {Structures}},
	isbn = {978-1-4673-6795-0},
	url = {http://ieeexplore.ieee.org/document/7371256/},
	doi = {10.1109/DICTA.2015.7371256},
	urldate = {2026-04-14},
	booktitle = {2015 {International} {Conference} on {Digital} {Image} {Computing}: {Techniques} and {Applications} ({DICTA})},
	publisher = {IEEE},
	author = {Youssef, Rabaa and Ricordeau, Anne and Sevestre-Ghalila, Sylvie and Benazza-Benyahya, Amel},
	month = nov,
	year = {2015},
	pages = {1--6},
}
