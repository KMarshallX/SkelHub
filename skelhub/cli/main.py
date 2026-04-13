"""Unified SkelHub CLI."""

from __future__ import annotations

import argparse
from typing import Optional

from skelhub.algorithms import MCPBackend  # noqa: F401 ensures backend registration
from skelhub.api import evaluate_prediction_path, run_algorithm_from_path
from skelhub.core import list_backends


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(prog="skelhub", description="Unified skeletonization framework CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a skeletonization backend.")
    run_parser.add_argument("--algorithm", required=True, choices=list_backends(), help="Backend to execute.")
    run_parser.add_argument("-i", "--input", required=True, help="Path to the input NIfTI volume.")
    run_parser.add_argument("-o", "--output", required=True, help="Path to the output skeleton NIfTI.")
    run_parser.add_argument(
        "--root-method",
        choices=("max_fdt", "topmost"),
        default="max_fdt",
        help="MCP root selection method.",
    )
    run_parser.add_argument("--threshold-scale", type=float, default=1.0, help="MCP branch threshold multiplier.")
    run_parser.add_argument(
        "--dilation-factor",
        type=float,
        default=2.0,
        help="MCP dilation factor applied to FDT radii.",
    )
    run_parser.add_argument("--max-iterations", type=int, default=200, help="MCP per-object iteration cap.")
    run_parser.add_argument(
        "--min-object-size",
        type=int,
        default=50,
        help="Ignore connected components smaller than this voxel count.",
    )
    run_parser.add_argument(
        "--label-objects",
        action="store_true",
        help="Write object labels instead of binary skeleton voxels.",
    )
    run_parser.add_argument("--verbose", action="store_true", help="Emit backend progress logs.")

    eval_parser = subparsers.add_parser("evaluate", help="Run the framework evaluation path.")
    eval_parser.add_argument("--pred", required=True, help="Skeleton NIfTI path to evaluate.")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_algorithm_from_path(
            algorithm=args.algorithm,
            input_path=args.input,
            output_path=args.output,
            config=args,
            log=print if args.verbose else None,
        )
        if args.verbose:
            print(
                f"framework run complete: algorithm={result.algorithm_name}, "
                f"output_voxels={int((result.skeleton > 0).sum())}"
            )
        return 0

    if args.command == "evaluate":
        result = evaluate_prediction_path(args.pred)
        print(result.message)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2
