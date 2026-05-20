"""Milestone 6 multi-object end-to-end tests."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

from tests import FIXTURES_DIR, save_skeleton_visualization
from skelhub.algorithms.mcp.multi_object import decompose, skeletonize_volume


TWO_TUBES_PATH = FIXTURES_DIR / "two_tubes.nii.gz"


def _load_fixture(path: Path) -> np.ndarray:
    """Load a fixture as float32."""
    return np.asarray(nib.load(str(path)).dataobj, dtype=np.float32)


def test_two_tubes_contains_skeletons_for_both_objects_without_cross_assignment() -> None:
    """Each disconnected tube should get its own skeleton voxels only inside its volume."""
    volume = _load_fixture(TWO_TUBES_PATH)
    skeleton_labels, metadata = skeletonize_volume(volume, min_size=1, label_objects=True)
    object_components = decompose(volume, min_size=1)

    save_skeleton_visualization(
        volume,
        skeleton_labels > 0,
        "two_tubes_overlay.png",
        "Milestone 6: two disconnected tubes",
    )

    assert metadata["num_objects"] == 2
    assert len(object_components) == 2

    for component_label, component_mask in object_components:
        component_skeleton = skeleton_labels == component_label
        other_object_mask = np.zeros_like(component_mask, dtype=bool)
        for other_label, other_mask in object_components:
            if other_label != component_label:
                other_object_mask |= other_mask

        assert np.any(component_skeleton & component_mask)
        assert not np.any(component_skeleton & other_object_mask)
