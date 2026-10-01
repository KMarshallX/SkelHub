"""Terminal and JSON reporting helpers for evaluation results."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from skelhub.core import CountComparison, EvaluationResult, ToleranceMatch


def format_evaluation_report(result: EvaluationResult, *, verbose: bool = False) -> str:
    """Format a terminal report. There is no combined score or pass/fail verdict."""
    geometry = result.geometry
    topology = result.topology
    lines = [
        "SkelHub Evaluation Report",
        f"Prediction: {result.pred_path or 'in-memory array'}",
        f"Reference: {result.ref_path or 'in-memory array'}",
        f"Status: {result.status}",
    ]
    if verbose:
        lines.append(f"Shape: {tuple(result.metadata.get('shape', ()))}")
        spacing = result.metadata.get("spacing_um")
        if spacing is not None:
            lines.append(f"Spacing: {tuple(round(float(value), 6) for value in spacing)} um")
        effective = result.metadata.get("effective_spatial_units", {})
        sources = result.metadata.get("spatial_unit_sources", {})
        header_units = result.metadata.get("source_spatial_units", {})
        lines.append(
            "Spatial units: "
            + ", ".join(
                f"{role}={effective.get(role)} (from {sources.get(role)}; header {header_units.get(role)})"
                for role in ("prediction", "reference")
            )
        )
        lines.append(
            f"Foreground voxels: prediction={result.metadata.get('pred_voxels')}, "
            f"reference={result.metadata.get('ref_voxels')}"
        )
        lines.append(
            f"Connectivity: foreground={topology.foreground_connectivity}, "
            f"background={topology.background_connectivity}"
        )

    lines.append("Geometry coverage:")
    if geometry.coverage_unavailable_reason:
        lines.append(f"  unavailable: {geometry.coverage_unavailable_reason}")
    for match in geometry.tolerances:
        lines.append(f"  {_tolerance_label(match)}: {_coverage_text(match)}")
        if verbose and match.f1 is not None:
            lines.append(
                "    matched/unmatched prediction voxels: "
                f"{match.matched_prediction_voxels}/{match.unmatched_prediction_voxels}; "
                "matched/unmatched reference voxels: "
                f"{match.matched_reference_voxels}/{match.unmatched_reference_voxels}"
            )

    lines.append("Geometry displacement:")
    distances = geometry.distances
    if distances is None:
        lines.append(f"  unavailable: {geometry.distances_unavailable_reason}")
    else:
        lines.append(
            f"  symmetric mean={_um(distances.symmetric_mean_um)}, "
            f"symmetric P95={_um(distances.symmetric_p95_um)}"
        )
        if verbose:
            lines.append(
                f"  pred->ref: mean={_um(distances.mean_pred_to_ref_um)}, "
                f"P95={_um(distances.p95_pred_to_ref_um)}, max={_um(distances.max_pred_to_ref_um)}"
            )
            lines.append(
                f"  ref->pred: mean={_um(distances.mean_ref_to_pred_um)}, "
                f"P95={_um(distances.p95_ref_to_pred_um)}, max={_um(distances.max_ref_to_pred_um)}"
            )
            lines.append(f"  Hausdorff (max)={_um(distances.hausdorff_um)}")

    lines.append("Topology (reference -> prediction):")
    for k, name in ((0, "components"), (1, "cycles"), (2, "cavities")):
        comparison = topology.comparison(k)
        lines.append(
            f"  {name} beta_{k}: {comparison.reference} -> {comparison.prediction} "
            f"(diff {comparison.signed_difference:+d})"
        )
    if verbose:
        lines.append(
            f"  Euler characteristic: {topology.reference.euler_characteristic} -> "
            f"{topology.prediction.euler_characteristic}"
        )
    lines.append(f"  Betti-count agreement: {'yes' if topology.betti_count_agreement else 'no'}")

    endpoints = result.endpoints
    lines.append(
        f"Endpoint diagnostics: reference={endpoints.reference}, prediction={endpoints.prediction} "
        f"(diff {endpoints.signed_difference:+d})"
    )

    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines)


def result_to_json_dict(result: EvaluationResult) -> dict[str, Any]:
    """Convert an evaluation result into a JSON-safe dictionary (no NaN/Infinity)."""
    geometry = result.geometry
    topology = result.topology
    unavailable = {}
    if geometry.coverage_unavailable_reason:
        unavailable["geometry.coverage"] = geometry.coverage_unavailable_reason
    if geometry.distances_unavailable_reason:
        unavailable["geometry.distances"] = geometry.distances_unavailable_reason

    return {
        "schema_version": result.schema_version,
        "status": result.status,
        "metadata": {
            "message": result.message,
            "pred_path": result.pred_path,
            "ref_path": result.ref_path,
            **result.metadata,
        },
        "config": dict(result.config),
        "geometry": {
            "primary_tolerance_um": geometry.primary.tolerance_um,
            "tolerances": [asdict(match) for match in geometry.tolerances],
            "distances_um": None if geometry.distances is None else asdict(geometry.distances),
        },
        "topology": {
            "foreground_connectivity": topology.foreground_connectivity,
            "background_connectivity": topology.background_connectivity,
            "reference": asdict(topology.reference),
            "prediction": asdict(topology.prediction),
            **{f"beta_{k}": _comparison_dict(topology.comparison(k)) for k in (0, 1, 2)},
            "betti_count_agreement": topology.betti_count_agreement,
        },
        "endpoint_diagnostics": _comparison_dict(result.endpoints),
        "warnings": list(result.warnings),
        "unavailable": unavailable,
    }


def write_evaluation_json(result: EvaluationResult, output_path: str | Path) -> Path:
    """Write the structured JSON report to disk."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_to_json_dict(result), indent=2, allow_nan=False), encoding="utf-8")
    return path


def _comparison_dict(comparison: CountComparison) -> dict[str, int]:
    return {
        "reference": comparison.reference,
        "prediction": comparison.prediction,
        "signed_difference": comparison.signed_difference,
        "absolute_error": comparison.absolute_error,
    }


def _tolerance_label(match: ToleranceMatch) -> str:
    label = f"@ {match.tolerance_um:g} um"
    if match.requested_unit == "voxels":
        label += f" ({match.requested_value:g} voxels)"
    return label + (" [primary]" if match.is_primary else "")


def _coverage_text(match: ToleranceMatch) -> str:
    if match.f1 is None:
        return "N/A"
    return f"F1={match.f1:.4f}, precision={match.precision:.4f}, recall={match.recall:.4f}"


def _um(value: float) -> str:
    return f"{value:.4g} um"
