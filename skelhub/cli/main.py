"""Unified SkelHub CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import skelhub.algorithms  # noqa: F401 ensures backend registration
from skelhub.api import (
    evaluate_prediction_path,
    generate_graphml_from_skeleton_path,
    launch_graph_viewer_from_path,
    run_algorithm_from_path,
)
from skelhub.visualization import GraphVisualizationError
from skelhub.core import list_backends
from skelhub.evaluation import format_evaluation_report, write_evaluation_json


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(prog="skelhub", description="Unified skeletonization framework CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a skeletonization backend.")
    run_parser.add_argument("--algorithm", required=True, choices=list_backends(), help="Backend to execute.")
    run_parser.add_argument("-i", "--input", required=True, help="Path to the input NIfTI volume.")
    run_parser.add_argument("-o", "--output", required=True, help="Path to the output skeleton NIfTI.")
    run_parser.add_argument(
        "--binarize-threshold",
        type=float,
        default=0.5,
        help="Threshold used by backends that require binary foreground conversion, such as lee94.",
    )
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

    eval_parser = subparsers.add_parser("evaluate", help="Evaluate a predicted skeleton against a reference.")
    eval_parser.add_argument("--pred", required=True, help="Predicted skeleton NIfTI path.")
    eval_parser.add_argument("--ref", required=True, help="Reference skeleton NIfTI path.")
    eval_parser.add_argument(
        "-b",
        "--buffer-radius",
        required=True,
        type=float,
        help="Buffer dilation radius used by the geometry-preservation metric.",
    )
    eval_parser.add_argument(
        "--buffer-radius-unit",
        choices=("voxels", "um"),
        default="voxels",
        help="Unit for --buffer-radius. Use 'um' for physical micrometers.",
    )
    eval_parser.add_argument(
        "--json-output",
        help="Optional path to write a structured JSON evaluation report.",
    )
    eval_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Emit progress logs and a detailed terminal report.",
    )

    graphgen_parser = subparsers.add_parser(
        "graphgen",
        help="Generate a Voreen-style proto-graph GraphML file from a skeleton NIfTI.",
    )
    graphgen_parser.add_argument("-i", "--input", required=True, help="Path to the input skeleton NIfTI.")
    graphgen_parser.add_argument("-o", "--output", required=True, help="Path to the output GraphML file.")
    graphgen_parser.add_argument("--verbose", action="store_true", help="Emit graph generation progress logs.")

    graphviz_parser = subparsers.add_parser(
        "graphviz",
        help="Open a 3D PyVista viewer for a GraphML vessel graph.",
    )
    graphviz_parser.add_argument(
        "-i",
        "--input",
        help="Optional path to an input GraphML file. If omitted, the viewer opens in an empty state.",
    )
    graphviz_parser.add_argument(
        "--edge_thickness",
        type=float,
        default=2.0,
        help="Rendered edge thickness in the 3D viewer.",
    )
    graphviz_parser.add_argument(
        "--node_size",
        type=float,
        default=6.0,
        help="Rendered node size in the 3D viewer.",
    )

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
        try:
            result = evaluate_prediction_path(
                args.pred,
                args.ref,
                buffer_radius=args.buffer_radius,
                buffer_radius_unit=args.buffer_radius_unit,
                log=print if args.verbose else None,
            )
            print(format_evaluation_report(result, verbose=args.verbose))
            if args.json_output:
                json_path = write_evaluation_json(result, Path(args.json_output))
                if args.verbose:
                    print(f"JSON report written to {json_path}")
            return 0
        except (FileNotFoundError, OSError, ValueError) as exc:
            parser.exit(status=2, message=f"skelhub evaluate: error: {exc}\n")

    if args.command == "graphgen":
        try:
            graph = generate_graphml_from_skeleton_path(
                args.input,
                args.output,
                log=print if args.verbose else None,
            )
            if args.verbose:
                print(
                    f"graphgen complete: nodes={len(graph.nodes)}, "
                    f"edges={len(graph.edges)}, output={args.output}"
                )
            return 0
        except (FileNotFoundError, OSError, ValueError) as exc:
            parser.exit(status=2, message=f"skelhub graphgen: error: {exc}\n")

    if args.command == "graphviz":
        try:
            return launch_graph_viewer_from_path(
                args.input,
                edge_thickness=args.edge_thickness,
                node_size=args.node_size,
            )
        except GraphVisualizationError as exc:
            parser.exit(status=2, message=f"skelhub graphviz: error: {exc}\n")

    parser.error(f"Unsupported command: {args.command}")
    return 2
