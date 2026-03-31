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
        "-r",
        choices=("max_fdt", "topmost"),
        default="max_fdt",
        help="Root selection method.",
    )
    parser.add_argument(
        "--threshold-scale",
        "-t",
        type=float,
        default=1.0,
        help="Significance threshold multiplier. Suggested value: 0.5 to include more branches but may introduce noise.",
    )
    parser.add_argument(
        "--dilation-factor",
        "-d",
        type=float,
        default=1.5,
        help="Scale factor applied to FDT when generating marked-mask dilation. Default: 2.0.",
    )
    parser.add_argument(
        "--min-object-size",
        "-s",
        type=int,
        default=50,
        help="Minimum component size in voxels.",
    )
    parser.add_argument(
        "--label-objects",
        "-l",
        action="store_true",
        help="Label object skeleton voxels by component index.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print per-object iteration, branch, and runtime reporting.",
    )
    parser.add_argument(
        "--max-iterations",
        "-it",
        type=int,
        default=200,
        help="Maximum skeleton-growth iterations per object before stopping safely.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> str:
    """Execute the multi-object skeleton pipeline."""
    data, affine, header = read_nifti(args.input)
    output_data, _metadata = skeletonize_volume(
        np.asarray(data, dtype=np.float32),
        root_method=args.root_method,
        threshold_scale=args.threshold_scale,
        dilation_factor=args.dilation_factor,
        max_iterations=args.max_iterations,
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
