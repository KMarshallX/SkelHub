# Evaluation

SkelHub evaluation is designed to be algorithm-agnostic. It should consume `SkeletonResult` outputs or standardized prediction files rather than backend internals.

Current status:

- Implemented: placeholder evaluation path in `skelhub.evaluation.placeholder`
- Input support: `.nii` and `.nii.gz` skeleton volumes
- Behavior: validates the file path, loads the NIfTI, checks dimensionality, and emits a clear success message

Current CLI:

```bash
skelhub evaluate --pred prediction_skeleton.nii.gz
```

Current limitation:

- No metrics are computed yet. The placeholder exists to establish the framework evaluation path cleanly before adding geometric or topological measures.
