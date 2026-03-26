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

- `--root-method {max_fdt,topmost}`
- `--threshold-scale FLOAT`
- `--max-iterations INT` maximum outer-loop iterations per object, default `200`
- `--min-object-size INT`
- `--label-objects`
- `--verbose`

Verbose mode reports, for each object:

- object index and component label
- iteration count
- branches added per iteration
- total significant branches detected
- wall-clock time per object

It also prints a final summary across all objects including average iterations per object and a complexity reference band `[log2(N), sqrt(N)]` for `N =` total terminal branches detected.

Output parent directories are created automatically, so validation commands can write directly to paths such as `./test_outputs/...` without manual setup.

## Validation Commands

Synthetic Milestone 7 acceptance runs:

```bash
python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_11.nii -o ./test_outputs/skel_m7_synthetic_11.nii.gz --verbose
python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_12.nii -o ./test_outputs/skel_m7_synthetic_12.nii.gz --verbose
python main.py -i ./test_data/synthetic_lsys_data/seg_sub015_i10_con_order1_test_13.nii -o ./test_outputs/skel_m7_synthetic_13.nii.gz --verbose
```

Real-data Milestone 7 acceptance run:

```bash
python main.py -i ./test_data/bigger_patch/bigCLIP_MASKED_sub_160um_seg.nii.gz -o ./test_outputs/skel_m7.nii.gz --verbose
```

## Citation


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
	file = {1-s2.0-S0167865515001063-main:C\:\\Users\\uqmxu4\\Zotero\\storage\\6DFKHIIP\\1-s2.0-S0167865515001063-main.pdf:application/pdf},
}


## Acknowledgement

This python project is copiloted by Codex (OpenAI).
