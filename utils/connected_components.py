"""Connected-component helpers for single-object subtree discovery."""

from __future__ import annotations

from typing import List, Tuple, cast

import numpy as np
from scipy import ndimage


_FULL_26_STRUCT = np.ones((3, 3, 3), dtype=np.uint8)


def label_subtrees(object_mask: np.ndarray, marked_mask: np.ndarray) -> List[Tuple[int, np.ndarray]]:
    """Label disconnected subtrees within a single object.

    Parameters
    ----------
    object_mask
        Boolean mask for one object.
    marked_mask
        Boolean mask for the already-covered region inside the same object.

    Returns
    -------
    list
        A list of `(label, subtree_mask)` tuples in descending voxel-count order.
    """
    object_support = np.asarray(object_mask, dtype=bool)
    marked = np.asarray(marked_mask, dtype=bool)

    if object_support.ndim != 3 or marked.ndim != 3:
        raise ValueError("label_subtrees expects 3D inputs.")
    if object_support.shape != marked.shape:
        raise ValueError("object_mask and marked_mask must have the same shape.")

    remainder = object_support & ~marked
    labeled, num_components = cast(
        Tuple[np.ndarray, int],
        ndimage.label(remainder, structure=_FULL_26_STRUCT),
    )

    subtrees: List[Tuple[int, np.ndarray]] = []
    for component_label in range(1, num_components + 1):
        subtree_mask = labeled == component_label
        if np.any(subtree_mask):
            subtrees.append((component_label, subtree_mask))

    subtrees.sort(key=lambda item: int(np.count_nonzero(item[1])), reverse=True)
    return subtrees
