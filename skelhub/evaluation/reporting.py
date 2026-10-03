"""Terminal and JSON reporting helpers for evaluation results."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from skelhub.core import CountComparison, EvaluationResult, ForegroundEdtAgreement, ForegroundEdtSummary, ToleranceMatch

from .foreground_edt import BOUNDARY_POLICY, FOREGROUND_EDT_DEFINITION, FOREGROUND_EDT_DISTANCE


FOREGROUND_EDT_TITLE = "Foreground EDT-sum Agreement"
FOREGROUND_EDT_NOT_COMPUTED = "Not computed\u2014no foreground mask supplied"


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

    lines.extend(_foreground_edt_lines(result.foreground_edt, verbose=verbose))

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
    unavailable.update(_foreground_edt_unavailable(result))

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
        "foreground_edt_agreement": _foreground_edt_dict(result.foreground_edt),
        "warnings": list(result.warnings),
        "unavailable": unavailable,
    }


def write_evaluation_json(result: EvaluationResult, output_path: str | Path) -> Path:
    """Write the structured JSON report to disk."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result_to_json_dict(result), indent=2, allow_nan=False), encoding="utf-8")
    return path


def _foreground_edt_lines(agreement: ForegroundEdtAgreement | None, *, verbose: bool) -> list[str]:
    lines = [f"{FOREGROUND_EDT_TITLE}:"]
    if agreement is None:
        return [*lines, f"  {FOREGROUND_EDT_NOT_COMPUTED}"]
    if verbose:
        mask = agreement.mask
        lines.append(
            f"  mask: {mask.path or 'in-memory array'}; units {mask.effective_spatial_unit} "
            f"(from {mask.spatial_unit_source}; header {mask.header_spatial_unit}); "
            f"foreground voxels={mask.foreground_voxels}; "
            f"touches image boundary: {'yes' if mask.touches_image_boundary else 'no'}"
        )
    for name, summary in (("reference", agreement.reference), ("prediction", agreement.prediction)):
        lines.append(f"  {name}: {_edt_summary_text(summary)}")
    if agreement.signed_relative_difference is None:
        lines.append(f"  relative difference: N/A ({agreement.relative_difference_unavailable_reason})")
    else:
        lines.append(
            f"  relative difference (pred - ref) / ref: {_percent(agreement.signed_relative_difference, signed=True)}"
            f" (absolute {_percent(agreement.absolute_relative_difference)})"
        )
    return lines


def _edt_summary_text(summary: ForegroundEdtSummary) -> str:
    text = f"EDT sum={summary.edt_sum_um:.6g} um, "
    if summary.mean_edt_um is None:
        return text + (
            f"mean=N/A, voxels={summary.skeleton_voxels}, outside mask={summary.outside_mask_voxels} "
            f"(fraction N/A: {summary.unavailable_reason})"
        )
    return text + (
        f"mean={_um(summary.mean_edt_um)}, voxels={summary.skeleton_voxels}, "
        f"outside mask={summary.outside_mask_voxels} ({_percent(summary.outside_mask_fraction)})"
    )


def _percent(fraction: float | None, *, signed: bool = False) -> str:
    if fraction is None:
        return "N/A"
    return f"{100.0 * fraction:{'+' if signed else ''}.2f}%"


def _foreground_edt_dict(agreement: ForegroundEdtAgreement | None) -> dict[str, Any] | None:
    if agreement is None:
        return None
    summary_fields = ("edt_sum_um", "mean_edt_um", "skeleton_voxels", "outside_mask_voxels", "outside_mask_fraction")
    return {
        "definition": FOREGROUND_EDT_DEFINITION,
        "distance": FOREGROUND_EDT_DISTANCE,
        "boundary_policy": BOUNDARY_POLICY,
        "mask": asdict(agreement.mask),
        "reference": {name: getattr(agreement.reference, name) for name in summary_fields},
        "prediction": {name: getattr(agreement.prediction, name) for name in summary_fields},
        "signed_relative_difference": agreement.signed_relative_difference,
        "absolute_relative_difference": agreement.absolute_relative_difference,
        "warnings": list(agreement.warnings),
    }


def _foreground_edt_unavailable(result: EvaluationResult) -> dict[str, str]:
    agreement = result.foreground_edt
    if agreement is None:
        return {"foreground_edt_agreement": str(result.foreground_edt_unavailable_reason)}
    unavailable = {}
    for name, summary in (("reference", agreement.reference), ("prediction", agreement.prediction)):
        for field in ("mean_edt_um", "outside_mask_fraction"):
            if getattr(summary, field) is None:
                unavailable[f"foreground_edt_agreement.{name}.{field}"] = str(summary.unavailable_reason)
    if agreement.signed_relative_difference is None:
        for field in ("signed_relative_difference", "absolute_relative_difference"):
            unavailable[f"foreground_edt_agreement.{field}"] = str(agreement.relative_difference_unavailable_reason)
    return unavailable


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
