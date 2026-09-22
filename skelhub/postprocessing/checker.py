"""Foreground confinement and component checks shared by CLI and GUI."""

from __future__ import annotations

from typing import Callable


def check_paths(
    foreground_input: str,
    skeleton_input: str,
    connectivity: int = 26,
    progress: Callable[[int | None, str], None] | None = None,
) -> None:
    """Print checker results, preserving the existing script report."""
    import sys
    from pathlib import Path

    def update(percent: int | None, message: str) -> None:
        if progress:
            progress(percent, message)

    try:
        import nibabel as nib
        import numpy as np
        from scipy import ndimage
    except ImportError as exc:
        print(f"Error: missing Python dependency: {exc.name}", file=sys.stderr)
        raise SystemExit(2) from exc


    def load_voxels(path: Path, label: str) -> np.ndarray:
        try:
            image = nib.load(str(path))
            return np.asanyarray(image.dataobj)
        except Exception as exc:
            print(f"Error: unable to read {label} NIfTI '{path}': {exc}", file=sys.stderr)
            raise SystemExit(2) from exc


    def report_nonbinary(values: np.ndarray, label: str) -> None:
        unique_values = np.unique(values)
        nonbinary = unique_values[(unique_values != 0) & (unique_values != 1)]
        if nonbinary.size:
            formatted = ", ".join(str(value.item()) for value in nonbinary)
            print(f"{label} non-binary values: [{formatted}]", file=sys.stderr)


    def load_graphml(path: Path):
        try:
            import igraph as ig
        except ImportError as exc:
            print("Error: missing Python dependency: igraph", file=sys.stderr)
            raise SystemExit(2) from exc
        try:
            return ig.Graph.Read_GraphML(str(path))
        except Exception as exc:
            print(f"Error: unable to read skeleton GraphML '{path}': {exc}", file=sys.stderr)
            raise SystemExit(2) from exc


    def parse_points(value: object, label: str, *, single: bool = False) -> np.ndarray:
        import json

        try:
            points = np.asarray(json.loads(str(value)), dtype=float)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {label} must contain JSON coordinates.", file=sys.stderr)
            raise SystemExit(2) from exc
        expected_shape = (3,) if single else None
        if single:
            valid_shape = points.shape == expected_shape
        else:
            valid_shape = points.ndim == 2 and points.shape[1:] == (3,)
        if not valid_shape or not np.isfinite(points).all():
            description = "three" if single else "a list of"
            print(
                f"Error: {label} must contain {description} finite 3D coordinates.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        return points.reshape((-1, 3))


    def points_are_confined(points: np.ndarray, foreground: np.ndarray) -> bool:
        """Test whether every point lies in at least one closed foreground cell."""
        if len(points) == 0:
            return True

        cell_radius = 0.5 + 1e-9
        foreground_shape = np.asarray(foreground.shape, dtype=np.int64)
        within_volume_extent = np.all(
            (points >= -cell_radius)
            & (points <= (foreground_shape - 1) + cell_radius),
            axis=1,
        )
        if not np.all(within_volume_extent):
            return False

        lowest_candidates = np.ceil(points - cell_radius).astype(np.int64)
        highest_candidates = np.floor(points + cell_radius).astype(np.int64)
        contained = np.zeros(len(points), dtype=bool)

        # A point can be in up to two closed cells per axis. Checking their Cartesian
        # product includes cells meeting the point at a shared face, edge, or corner.
        for offset in np.ndindex(2, 2, 2):
            candidates = lowest_candidates + np.asarray(offset, dtype=np.int64)
            valid = np.all(
                (candidates <= highest_candidates)
                & (candidates >= 0)
                & (candidates < foreground_shape),
                axis=1,
            )
            unchecked = valid & ~contained
            if np.any(unchecked):
                contained[unchecked] = (
                    foreground[tuple(candidates[unchecked].T)] != 0
                )

        return bool(np.all(contained))


    def report_graphml(graph, foreground: np.ndarray, foreground_affine: np.ndarray) -> None:
        vertex_attributes = set(graph.vs.attributes())
        if graph.vcount() and "voxel_pos" not in vertex_attributes:
            print("Error: GraphML nodes must provide 'voxel_pos'.", file=sys.stderr)
            raise SystemExit(2)

        update(None, f"Checking voxel positions for {graph.vcount()} graph nodes")
        node_points = np.vstack(
            [
                parse_points(vertex["voxel_pos"], f"node {vertex.index} voxel_pos", single=True)
                for vertex in graph.vs
            ]
        ) if graph.vcount() else np.empty((0, 3), dtype=float)
        nodes_contained = "Yes" if points_are_confined(node_points, foreground) else "No"
        print(f"Are all graph node voxel_pos points contained within foreground: {nodes_contained}")
        update(None, f"Node confinement result: {nodes_contained}")

        edge_coordinate_fields = (
            ("centerline_voxels", False),
            ("centerline_voxel_points", False),
            ("centerline_world_points", True),
        )
        edge_attributes = set(graph.es.attributes())
        available_edge_fields = [
            field for field, _ in edge_coordinate_fields if field in edge_attributes
        ]
        if graph.ecount() and not available_edge_fields:
            supported = ", ".join(field for field, _ in edge_coordinate_fields)
            print(
                "Error: GraphML edges must provide at least one supported coordinate "
                f"field: {supported}.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        for field, is_world_coordinates in edge_coordinate_fields:
            if field not in edge_attributes:
                continue
            update(None, f"Checking {field} for {graph.ecount()} graph edges")
            field_points = np.vstack(
                [parse_points(edge[field], f"edge {edge.index} {field}") for edge in graph.es]
            ) if graph.ecount() else np.empty((0, 3), dtype=float)
            if is_world_coordinates and len(field_points):
                try:
                    world_to_voxel = np.linalg.inv(foreground_affine)
                except np.linalg.LinAlgError as exc:
                    print("Error: foreground affine is singular.", file=sys.stderr)
                    raise SystemExit(2) from exc
                field_points = nib.affines.apply_affine(world_to_voxel, field_points)
            contained = "Yes" if points_are_confined(field_points, foreground) else "No"
            print(f"Are all graph edge {field} points contained within foreground: {contained}")
            update(None, f"Edge {field} confinement result: {contained}")

        graph_component_count = len(graph.connected_components(mode="weak"))
        print(f"Graph connected-components number: {graph_component_count}")


    foreground_path = Path(foreground_input)
    skeleton_path = Path(skeleton_input)
    connectivity = int(connectivity)
    update(10, f"Loading foreground volume: {foreground_path.name}")
    try:
        foreground_image = nib.load(str(foreground_path))
        foreground = np.asanyarray(foreground_image.dataobj)
    except Exception as exc:
        print(f"Error: unable to read foreground NIfTI '{foreground_path}': {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if foreground.ndim != 3:
        print(
            f"Error: foreground must be a 3D volume, got {foreground.ndim}D.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    report_nonbinary(foreground, "Foreground")

    connectivity_rank = {6: 1, 18: 2, 26: 3}[connectivity]
    structure = ndimage.generate_binary_structure(rank=3, connectivity=connectivity_rank)
    _, foreground_component_count = ndimage.label(foreground != 0, structure=structure)
    update(45, f"Foreground loaded: {foreground.shape}; {foreground_component_count} components at {connectivity}-connectivity")

    if skeleton_path.suffix.lower() == ".graphml":
        update(55, f"Loading GraphML: {skeleton_path.name}")
        graph = load_graphml(skeleton_path)
        update(None, f"Checking {graph.vcount()} nodes and {graph.ecount()} edges against occupied voxel cells")
        report_graphml(graph, foreground, foreground_image.affine)
        print(f"Foreground connected-components number: {foreground_component_count}")
        update(95, "Graph confinement and component checks complete")
        raise SystemExit(0)

    update(55, f"Loading skeleton volume: {skeleton_path.name}")
    skeleton = load_voxels(skeleton_path, "skeleton")
    if foreground.shape != skeleton.shape:
        print(
            "Error: foreground and skeleton shapes differ: "
            f"{foreground.shape} != {skeleton.shape}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if skeleton.ndim != 3:
        print(
            f"Error: foreground and skeleton must be 3D volumes, got {skeleton.ndim}D.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    report_nonbinary(skeleton, "Skeleton")
    _, skeleton_component_count = ndimage.label(skeleton != 0, structure=structure)

    escaping_voxels = (skeleton != 0) & (foreground == 0)
    contained = "No" if np.any(escaping_voxels) else "Yes"
    print(f"Are all skeleton voxels contained within foreground: {contained}")
    print(f"Foreground connected-components number: {foreground_component_count}")
    print(f"Skeleton connected-components number: {skeleton_component_count}")
    update(95, f"Skeleton check complete: {skeleton_component_count} skeleton components")


if __name__ == "__main__":
    import sys
    check_paths(*sys.argv[1:])
