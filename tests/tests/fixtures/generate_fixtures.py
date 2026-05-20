"""Generate synthetic NIfTI fixtures for skeletonization tests."""

from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage


SCRIPT_DIR = Path(__file__).resolve().parent


def _save_nifti(volume: np.ndarray, name: str) -> None:
    """Save a fixture volume with identity affine."""
    output_path = SCRIPT_DIR / name
    if np.issubdtype(volume.dtype, np.floating):
        data = volume.astype(np.float32, copy=False)
    else:
        data = volume.astype(np.uint8, copy=False)
    image = nib.Nifti1Image(data, affine=np.eye(4, dtype=np.float32))
    nib.save(image, str(output_path))


def _tube_along_z(shape: tuple[int, int, int], center_y: int, center_x: int, radius: int) -> np.ndarray:
    """Create a cylindrical binary tube oriented along z axis in `(z, y, x)` indexing."""
    z, y, x = np.indices(shape)
    _ = z  # Explicitly unused; tube spans all z slices.
    radial = np.sqrt((y - center_y) ** 2 + (x - center_x) ** 2)
    return radial <= radius


def _add_sphere(volume: np.ndarray, center: tuple[int, int, int], radius: int) -> None:
    """Add an in-place spherical protrusion to a binary volume."""
    cz, cy, cx = center
    z0 = max(0, cz - radius)
    z1 = min(volume.shape[0], cz + radius + 1)
    y0 = max(0, cy - radius)
    y1 = min(volume.shape[1], cy + radius + 1)
    x0 = max(0, cx - radius)
    x1 = min(volume.shape[2], cx + radius + 1)

    zz, yy, xx = np.indices((z1 - z0, y1 - y0, x1 - x0))
    zz = zz + z0
    yy = yy + y0
    xx = xx + x0
    sphere = ((zz - cz) ** 2 + (yy - cy) ** 2 + (xx - cx) ** 2) <= radius**2
    volume[z0:z1, y0:y1, x0:x1] |= sphere


def _fuzzify_binary_volume(volume: np.ndarray, min_membership: float = 0.2) -> np.ndarray:
    """Create a fuzzy counterpart with the same support and stronger interior memberships."""
    object_mask = volume.astype(bool)
    if not np.any(object_mask):
        return np.zeros_like(volume, dtype=np.float32)

    edt = ndimage.distance_transform_edt(object_mask).astype(np.float32)
    normalized = np.zeros_like(edt, dtype=np.float32)
    normalized[object_mask] = edt[object_mask] / float(np.max(edt[object_mask]))

    fuzzy = np.zeros_like(edt, dtype=np.float32)
    fuzzy[object_mask] = min_membership + (1.0 - min_membership) * normalized[object_mask]
    return fuzzy


def generate_straight_tube() -> np.ndarray:
    """Generate `straight_tube.nii.gz` fixture."""
    shape = (20, 20, 60)
    volume = _tube_along_z(shape, center_y=10, center_x=30, radius=3)
    return volume.astype(np.uint8)


def generate_y_tube() -> np.ndarray:
    """Generate `y_tube.nii.gz` fixture."""
    shape = (40, 40, 60)
    volume = np.zeros(shape, dtype=bool)

    # Trunk: radius 3 from z=0..30 at center (y=20, x=20)
    z, y, x = np.indices(shape)
    trunk = (z <= 30) & (((y - 20) ** 2 + (x - 20) ** 2) <= 3**2)
    volume |= trunk

    # Branch 1: +x direction, fixed z=30, radius 2 tube in y-z plane around line.
    branch1 = (
        (x >= 20)
        & (x <= 39)
        & (((y - 20) ** 2 + (z - 30) ** 2) <= 2**2)
    )
    volume |= branch1

    # Branch 2: +y direction, fixed z=30, radius 2 tube in x-z plane around line.
    branch2 = (
        (y >= 20)
        & (y <= 39)
        & (((x - 20) ** 2 + (z - 30) ** 2) <= 2**2)
    )
    volume |= branch2

    return volume.astype(np.uint8)


def generate_y_tube_noisy() -> np.ndarray:
    """Generate `y_tube_noisy.nii.gz` with random boundary protrusions."""
    rng = np.random.default_rng(42)
    volume = generate_y_tube().astype(bool)

    eroded = ndimage.binary_erosion(
        volume, structure=np.ones((3, 3, 3), dtype=bool)
    ).astype(bool)
    boundary = volume & ~eroded
    boundary_coords = np.argwhere(boundary)

    if boundary_coords.size > 0:
        num_samples = max(1, int(0.01 * boundary_coords.shape[0]))
        picked_idx = rng.choice(boundary_coords.shape[0], size=num_samples, replace=False)
        for idx in picked_idx:
            cz, cy, cx = boundary_coords[idx]
            radius = int(rng.integers(1, 3))
            _add_sphere(volume, (int(cz), int(cy), int(cx)), radius)

    return volume.astype(np.uint8)


def generate_two_tubes() -> np.ndarray:
    """Generate `two_tubes.nii.gz` with two disconnected straight tubes."""
    shape = (60, 20, 60)
    volume = np.zeros(shape, dtype=bool)

    tube1 = _tube_along_z(shape, center_y=10, center_x=15, radius=3)
    tube2 = _tube_along_z(shape, center_y=10, center_x=45, radius=3)

    volume |= tube1
    volume |= tube2
    return volume.astype(np.uint8)


def generate_fuzzy_straight_tube() -> np.ndarray:
    """Generate `fuzzy_straight_tube.nii.gz` fixture."""
    return _fuzzify_binary_volume(generate_straight_tube())


def generate_fuzzy_y_tube() -> np.ndarray:
    """Generate `fuzzy_y_tube.nii.gz` fixture."""
    return _fuzzify_binary_volume(generate_y_tube())


def main() -> None:
    """Generate and save all synthetic fixtures."""
    _save_nifti(generate_straight_tube(), "straight_tube.nii.gz")
    _save_nifti(generate_y_tube(), "y_tube.nii.gz")
    _save_nifti(generate_y_tube_noisy(), "y_tube_noisy.nii.gz")
    _save_nifti(generate_two_tubes(), "two_tubes.nii.gz")
    _save_nifti(generate_fuzzy_straight_tube(), "fuzzy_straight_tube.nii.gz")
    _save_nifti(generate_fuzzy_y_tube(), "fuzzy_y_tube.nii.gz")


if __name__ == "__main__":
    main()
