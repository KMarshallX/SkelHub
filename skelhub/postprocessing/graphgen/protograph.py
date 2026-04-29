"""ProtoGraph construction mirroring Voreen's skeleton-to-protograph stage."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .components import SkeletonComponents, Voxel, are_26_neighbors


@dataclass(slots=True)
class ProtoGraphNode:
    """A proto-graph node derived from endpoint, branch, or loop support voxels."""

    id: int
    voxels: list[Voxel]
    kind: str
    at_sample_border: bool
    edges: list[int] = field(default_factory=list)

    @property
    def voxel_pos(self) -> tuple[float, float, float]:
        coords = np.asarray(self.voxels, dtype=float)
        pos = coords.mean(axis=0)
        return (float(pos[0]), float(pos[1]), float(pos[2]))


@dataclass(slots=True)
class ProtoGraphEdge:
    """A proto-graph edge with an ordered regular centerline path."""

    id: int
    node1: int
    node2: int
    voxels: list[Voxel]


@dataclass(slots=True)
class ProtoGraph:
    """Skeleton-derived topology before segmentation-derived vessel features."""

    shape: tuple[int, int, int]
    affine: np.ndarray
    nodes: list[ProtoGraphNode] = field(default_factory=list)
    edges: list[ProtoGraphEdge] = field(default_factory=list)

    def insert_node(self, voxels: list[Voxel], kind: str) -> int:
        node_id = len(self.nodes)
        node = ProtoGraphNode(
            id=node_id,
            voxels=list(voxels),
            kind=kind,
            at_sample_border=any(_at_sample_border(voxel, self.shape) for voxel in voxels),
        )
        self.nodes.append(node)
        return node_id

    def insert_edge(self, node1: int, node2: int, voxels: list[Voxel]) -> int:
        edge_id = len(self.edges)
        edge = ProtoGraphEdge(id=edge_id, node1=node1, node2=node2, voxels=list(voxels))
        self.edges.append(edge)
        self.nodes[node1].edges.append(edge_id)
        self.nodes[node2].edges.append(edge_id)
        return edge_id


def _at_sample_border(voxel: Voxel, shape: tuple[int, int, int]) -> bool:
    return any(voxel[axis] == 0 or voxel[axis] >= shape[axis] - 1 for axis in range(3))


def _build_node_voxel_map(graph: ProtoGraph) -> dict[Voxel, int]:
    node_voxels: dict[Voxel, int] = {}
    for node in graph.nodes:
        for voxel in node.voxels:
            node_voxels[voxel] = node.id
    return node_voxels


def _find_neighbor_nodes(node_voxels: dict[Voxel, int], voxel: Voxel) -> list[int]:
    neighbor_ids = {
        node_id
        for node_voxel, node_id in node_voxels.items()
        if are_26_neighbors(node_voxel, voxel)
    }
    return sorted(neighbor_ids)


def build_protograph(
    components: SkeletonComponents,
    shape: tuple[int, int, int],
    affine: np.ndarray | None = None,
) -> ProtoGraph:
    """Build a proto-graph from connected skeleton components."""
    graph = ProtoGraph(
        shape=tuple(int(v) for v in shape),
        affine=np.eye(4, dtype=float) if affine is None else np.asarray(affine, dtype=float),
    )

    for endpoint in components.endpoints:
        graph.insert_node([endpoint], kind="endpoint")
    for branch_component in components.branch_components:
        graph.insert_node(branch_component, kind="branch")

    node_voxels = _build_node_voxel_map(graph)
    for regular_component in components.regular_components:
        if not regular_component:
            continue
        left_end = regular_component[0]
        right_end = regular_component[-1]
        left_neighbors = _find_neighbor_nodes(node_voxels, left_end)
        right_neighbors = _find_neighbor_nodes(node_voxels, right_end)

        if left_end == right_end:
            neighbor_ids = _find_neighbor_nodes(node_voxels, left_end)
            if len(neighbor_ids) >= 2:
                graph.insert_edge(neighbor_ids[0], neighbor_ids[1], regular_component)
            continue

        if not left_neighbors and not right_neighbors:
            if not are_26_neighbors(left_end, right_end):
                continue
            new_node = graph.insert_node([left_end, right_end], kind="synthetic_loop")
            node_voxels[left_end] = new_node
            node_voxels[right_end] = new_node
            graph.insert_edge(new_node, new_node, regular_component)
            continue

        if len(left_neighbors) == 1 and len(right_neighbors) == 1:
            graph.insert_edge(left_neighbors[0], right_neighbors[0], regular_component)

    node_voxels = _build_node_voxel_map(graph)
    for node in list(graph.nodes):
        if node.edges:
            continue
        for voxel in node.voxels:
            neighbor_ids = _find_neighbor_nodes(node_voxels, voxel)
            neighbor_ids = [neighbor_id for neighbor_id in neighbor_ids if neighbor_id != node.id]
            if neighbor_ids:
                graph.insert_edge(neighbor_ids[0], node.id, [])
                break

    return graph


def voxel_to_world(affine: np.ndarray, voxel: tuple[float, float, float]) -> tuple[float, float, float]:
    """Transform a voxel coordinate into world space using a NIfTI affine."""
    homogeneous = np.asarray([voxel[0], voxel[1], voxel[2], 1.0], dtype=float)
    world = np.asarray(affine, dtype=float) @ homogeneous
    return (float(world[0]), float(world[1]), float(world[2]))
