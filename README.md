# Curve Skeletonization

This project implements a NIfTI-based curve skeletonization pipeline inspired by Jin et al. for tree-like 3D objects. The current milestone includes end-to-end multi-object skeleton extraction plus Milestone 7 runtime reporting, iteration safety caps, and validation-ready CLI behavior.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python main.py -i /path/to/input.nii.gz -o /path/to/out.nii.gz
```

Optional arguments:

- `--root-method {max_fdt,topmost}` controls how the root voxel is chosen for each disconnected object.
  Use `max_fdt` (default) to start from the deepest interior voxel. Use `topmost` to prefer a root near the top of the object, which can be useful for airway-like data with a known superior-to-inferior orientation.
- `--threshold-scale FLOAT` multiplies the branch-significance acceptance threshold. The default is `1.0`.
  Increase it to make branch acceptance more conservative and reduce weak side branches. Decrease it slightly to keep more marginal branches. The value must be positive.
- `--dilation-factor FLOAT` scales the FDT value used when generating the marked-mask dilation around the root and accepted branches. The default is `2.0`.
  Leaving it unset preserves the current behavior, where the dilation radius is `2 * FDT(p)` at each branch voxel. The value must be positive.
- `--max-iterations INT` sets the maximum number of outer skeleton-growth iterations per object. Default: `200`.
  This is a safety cap for complex or pathological inputs. If the cap is reached, the program stops growing that object safely and reports it in verbose mode.
- `--min-object-size INT` ignores connected components smaller than the given voxel count. Default: `50`.
  This is useful for filtering out isolated specks or segmentation noise before skeletonization begins.
- `--label-objects` writes each object's skeleton voxels using its connected-component label instead of writing all skeleton voxels as `1`.
  This is useful when the input volume contains multiple disconnected trees and you want to keep them distinguishable in the output.
- `--verbose` prints progress and runtime reporting during processing.

Example with optional arguments:

```bash
python main.py \
  -i /path/to/input.nii.gz \
  -o /path/to/out.nii.gz \
  --root-method topmost \
  --threshold-scale 1.1 \
  --dilation-factor 2.0 \
  --min-object-size 100 \
  --max-iterations 300 \
  --label-objects \
  --verbose
```

Verbose mode reports, for each object:

- object index and component label
- iteration count
- branches added per iteration
- total significant branches detected
- wall-clock time per object

It also prints a final summary across all objects including average iterations per object and a complexity reference band `[log2(N), sqrt(N)]` for `N =` total terminal branches detected.

Output parent directories are created automatically, so validation commands can write directly to paths such as `./test_outputs/...` without manual setup.

## Citation
Original paper: _A robust and efficient curve skeletonization algorithm for tree-like objects using minimum cost paths_ (Jin et al., 2016)

@article{jin_robust_2016,
	title = {A robust and efficient curve skeletonization algorithm for tree-like objects using minimum cost paths},
	volume = {76},
	issn = {01678655},
	url = {https://linkinghub.elsevier.com/retrieve/pii/S0167865515001063},
	doi = {10.1016/j.patrec.2015.04.002},
	language = {en},
	urldate = {2025-10-13},
	journal = {Pattern Recognition Letters},
	author = {Jin, Dakai and Iyer, Krishna S. and Chen, Cheng and Hoffman, Eric A. and Saha, Punam K.},
	month = jun,
	year = {2016},
	pages = {32--40},
}


## Acknowledgement

This python project is copiloted by Codex (OpenAI).
