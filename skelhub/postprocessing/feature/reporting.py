"""CSV output for feature extraction."""

from __future__ import annotations

import csv
from pathlib import Path

from .models import FeatureExtractionResult


def write_feature_csvs(
    result: FeatureExtractionResult,
    edge_output_path: str | Path,
    node_output_path: str | Path,
) -> None:
    """Write edge and node feature records as two CSV files."""
    suffix = result.physical_unit
    edge_headers = [
        "id",
        "node1_id",
        "node2_id",
        "length",
        "minRadius",
        "avgRadius",
        "maxRadius",
        "curveness",
        "node1_degree",
        "node2_degree",
        f"length_image_{suffix}",
        f"minRadius_image_{suffix}",
        f"avgRadius_image_{suffix}",
        f"maxRadius_image_{suffix}",
        "curveness_image",
    ]
    edge_path = Path(edge_output_path)
    edge_path.parent.mkdir(parents=True, exist_ok=True)
    with edge_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(edge_headers)
        for row in result.edges:
            writer.writerow(
                [
                    row.id,
                    row.node1_id,
                    row.node2_id,
                    row.length,
                    row.minRadius,
                    row.avgRadius,
                    row.maxRadius,
                    row.curveness,
                    row.node1_degree,
                    row.node2_degree,
                    row.length_image,
                    row.minRadius_image,
                    row.avgRadius_image,
                    row.maxRadius_image,
                    row.curveness_image,
                ]
            )

    node_path = Path(node_output_path)
    node_path.parent.mkdir(parents=True, exist_ok=True)
    with node_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "position_x", "position_y", "position_z", "degree"])
        for row in result.nodes:
            writer.writerow([row.id, row.position_x, row.position_y, row.position_z, row.degree])
