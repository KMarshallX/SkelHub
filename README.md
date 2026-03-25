# Curve Skeletonization

This project implements the early milestones of a NIfTI-based curve skeletonization pipeline inspired by Jin et al. Milestone 3 adds local significance factor (LSF) computation and geometric geodesic distance support on top of the existing fuzzy distance transform and fuzzy maximal-ball detection pipeline.

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
- `--min-object-size INT`
- `--label-objects`

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
