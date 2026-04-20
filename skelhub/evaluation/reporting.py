"""Terminal and JSON reporting helpers for evaluation results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skelhub.core import EvaluationResult


def format_evaluation_report(result: EvaluationResult, *, verbose: bool = False) -> str:
    """Format a terminal report for an evaluation result."""
    lines = [
        "SkelHub Evaluation Report",
        f"Prediction: {result.pred_path or result.input_path or 'N/A'}",
        f"Reference: {result.ref_path or 'N/A'}",
        (
            f"Buffer radius: {_format_float(result.buffer_radius)} {result.buffer_radius_unit or 'unknown'} "
            f"(mode={result.buffer_radius_mode or 'unknown'})"
        ),
    ]

    spacing = result.metadata.get("spacing")
    shape = result.metadata.get("shape")
    spatial_unit = result.metadata.get("spacing_unit", "unknown")
    if verbose and shape is not None:
        lines.append(f"Shape: {tuple(shape)}")
    if verbose and spacing is not None:
        lines.append(f"Spacing: {tuple(spacing)} [{spatial_unit}]")
        lines.append(
            "Connectivity: "
            f"foreground={result.foreground_connectivity}, background={result.background_connectivity}"
        )

    lines.append(
        "Geometry: "
        f"TP={result.TP}, FP={result.FP}, FN={result.FN}, "
        f"Cp={_format_float(result.Cp)}, Cr={_format_float(result.Cr)}"
    )

    if verbose:
        lines.append(
            "Morphology: "
            f"OCC={_format_float(result.OCC)} "
            f"(clipped={_format_float(result.OCC_clipped)}, normalized={_format_float(result.OCC_normalized)})"
        )
        lines.append(
            "            "
            f"BCC={_format_float(result.BCC)} "
            f"(clipped={_format_float(result.BCC_clipped)}, normalized={_format_float(result.BCC_normalized)})"
        )
        lines.append(
            "            "
            f"E={_format_float(result.E)} "
            f"(clipped={_format_float(result.E_clipped)}, normalized={_format_float(result.E_normalized)})"
        )
    else:
        lines.append(
            "Morphology raw: "
            f"OCC={_format_float(result.OCC)}, "
            f"BCC={_format_float(result.BCC)}, "
            f"E={_format_float(result.E)}"
        )

    lines.append(f"Global performance score P: {_format_float(result.P)}")

    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)

    return "\n".join(lines)


def result_to_json_dict(result: EvaluationResult) -> dict[str, Any]:
    """Convert an evaluation result into a structured JSON-safe dictionary."""
    metadata = {
        "message": result.message,
        "pred_path": result.pred_path,
        "ref_path": result.ref_path,
        "shape": _tuple_to_list(result.metadata.get("shape")),
        "spacing": _tuple_to_list(result.metadata.get("spacing")),
        "spacing_unit": result.metadata.get("spacing_unit"),
        "pred_voxels": result.metadata.get("pred_voxels"),
        "ref_voxels": result.metadata.get("ref_voxels"),
        "supporting_counts": result.metadata.get("supporting_counts", {}),
    }
    config = {
        "buffer_radius": result.buffer_radius,
        "buffer_radius_unit": result.buffer_radius_unit,
        "buffer_radius_mode": result.buffer_radius_mode,
        "buffer_radius_voxel_equivalent": _tuple_to_list(
            result.metadata.get("buffer_radius_voxel_equivalent")
        ),
        "foreground_connectivity": result.foreground_connectivity,
        "background_connectivity": result.background_connectivity,
    }
    raw_metrics = {
        "TP": result.TP,
        "FP": result.FP,
        "FN": result.FN,
        "OCC": result.OCC,
        "OCC_clipped": result.OCC_clipped,
        "BCC": result.BCC,
        "BCC_clipped": result.BCC_clipped,
        "E": result.E,
        "E_clipped": result.E_clipped,
    }
    normalized_metrics = {
        "Cp": result.Cp,
        "Cr": result.Cr,
        "OCC_normalized": result.OCC_normalized,
        "BCC_normalized": result.BCC_normalized,
        "E_normalized": result.E_normalized,
        "P": result.P,
    }
    return {
        "metadata": metadata,
        "config": config,
        "raw_metrics": raw_metrics,
        "normalized_metrics": normalized_metrics,
        "warnings": list(result.warnings),
    }


def write_evaluation_json(result: EvaluationResult, output_path: str | Path) -> Path:
    """Write the structured JSON report to disk."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_to_json_dict(result), indent=2), encoding="utf-8")
    return path


def _format_float(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.4f}"


def _tuple_to_list(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    return value
