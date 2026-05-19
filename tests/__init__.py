"""Test helpers and package metadata."""

from __future__ import annotations

from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
ARTIFACTS_DIR = REPO_ROOT / "outputs" / "milestone2"
MILESTONE6_FIGURES_DIR = REPO_ROOT / "outputs" / "figures_m6"


def _get_pyplot():
    """Import matplotlib lazily so unrelated tests do not require it at collection time."""
    import matplotlib

    matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    return plt


def save_tube_visualization(
    volume: np.ndarray,
    fdt: np.ndarray,
    fcmb_mask: np.ndarray,
    output_name: str,
) -> Path:
    """Save a non-interactive visualization for Milestone 2 acceptance checks."""
    plt = _get_pyplot()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    z_index = volume.shape[0] // 2
    object_slice = volume[z_index]
    fdt_slice = fdt[z_index]
    fcmb_slice = fcmb_mask[z_index]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)

    axes[0].imshow(object_slice, cmap="gray", origin="lower")
    axes[0].set_title("Input object")
    axes[0].axis("off")

    fdt_image = axes[1].imshow(fdt_slice, cmap="magma", origin="lower")
    axes[1].set_title("FDT")
    axes[1].axis("off")
    fig.colorbar(fdt_image, ax=axes[1], fraction=0.046, pad=0.04)

    axes[2].imshow(object_slice, cmap="gray", origin="lower", alpha=0.55)
    axes[2].imshow(fdt_slice, cmap="magma", origin="lower", alpha=0.5)
    axes[2].contour(fcmb_slice.astype(np.uint8), levels=[0.5], colors="cyan", linewidths=1.2)
    axes[2].set_title("fCMB overlay")
    axes[2].axis("off")

    output_path = ARTIFACTS_DIR / output_name
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_skeleton_visualization(
    volume: np.ndarray,
    skeleton: np.ndarray,
    output_name: str,
    title: str,
) -> Path:
    """Save non-interactive MIP overlays for Milestone 6 acceptance checks."""
    plt = _get_pyplot()
    MILESTONE6_FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    object_mask = np.asarray(volume) > 0
    skeleton_mask = np.asarray(skeleton) > 0
    projections = [
        ("Axial MIP", np.max(object_mask, axis=0), np.max(skeleton_mask, axis=0)),
        ("Coronal MIP", np.max(object_mask, axis=1), np.max(skeleton_mask, axis=1)),
        ("Sagittal MIP", np.max(object_mask, axis=2), np.max(skeleton_mask, axis=2)),
    ]

    fig, axes = plt.subplots(3, 3, figsize=(12, 12), constrained_layout=True)
    fig.suptitle(title)

    for column, (projection_title, object_projection, skeleton_projection) in enumerate(projections):
        axes[0, column].imshow(object_projection, cmap="gray", origin="lower")
        axes[0, column].set_title(f"{projection_title}: object")
        axes[0, column].axis("off")

        axes[1, column].imshow(skeleton_projection, cmap="hot", origin="lower")
        axes[1, column].set_title(f"{projection_title}: skeleton")
        axes[1, column].axis("off")

        axes[2, column].imshow(object_projection, cmap="gray", origin="lower", alpha=0.7)
        axes[2, column].imshow(skeleton_projection, cmap="autumn", origin="lower", alpha=0.85)
        axes[2, column].set_title(f"{projection_title}: overlay")
        axes[2, column].axis("off")

    output_path = MILESTONE6_FIGURES_DIR / output_name
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path
