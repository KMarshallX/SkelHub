"""CLI entry point for the curve-skeletonization pipeline."""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
from typing import Optional

import numpy as np
from utils.multi_object import skeletonize_volume

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent


def _load_function(module_path: pathlib.Path, function_name: str):
    """Load a function from a local module path.

    This avoids the import-name conflict between this project's `io/` package and
    Python's standard library `io` module while keeping the required file layout.
    """
    module_name = f"_local_{module_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module at {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function_name)


read_nifti = _load_function(PROJECT_ROOT / "io" / "nifti_reader.py", "read_nifti")
write_nifti = _load_function(PROJECT_ROOT / "io" / "nifti_writer.py", "write_nifti")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for the skeletonization CLI."""
    parser = argparse.ArgumentParser(
        description="Curve skeletonization pipeline (Milestone 1 scaffold)."
    )
    parser.add_argument("-i", "--input", required=True, help="Path to input NIfTI file")
    parser.add_argument("-o", "--output", required=True, help="Path to output NIfTI file")
    parser.add_argument(
        "--root-method",
        choices=("max_fdt", "topmost"),
        default="max_fdt",
        help="Root selection method (reserved for later milestones).",
    )
    parser.add_argument(
        "--threshold-scale",
        type=float,
        default=1.0,
        help="Significance threshold multiplier (reserved for later milestones).",
    )
    parser.add_argument(
        "--min-object-size",
        type=int,
        default=50,
        help="Minimum component size in voxels (reserved for later milestones).",
    )
    parser.add_argument(
        "--label-objects",
        action="store_true",
        help="Label object skeleton voxels by component index.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-object progress and branch counts.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> str:
    """Execute the Milestone 6 multi-object skeleton pipeline."""
    data, affine, header = read_nifti(args.input)
    output_data, _metadata = skeletonize_volume(
        np.asarray(data, dtype=np.float32),
        root_method=args.root_method,
        threshold_scale=args.threshold_scale,
        min_size=args.min_object_size,
        label_objects=args.label_objects,
        log=print if args.verbose else None,
    )
    return write_nifti(output_data, affine, header, args.output)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI main function."""
    args = parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
