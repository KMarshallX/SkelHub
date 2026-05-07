"""Small-cycle refinement for the Laplacian backend."""

from __future__ import annotations

import networkx as nx
import numpy as np

from .base_graph import BaseGraph
from .tools import cycle_area


class RefineGraph(BaseGraph):
    """Collapse small polygon artifacts left after contraction."""

    def __init__(self, graph=None):
        super().__init__()
        self.Graph = graph

    def _refine_graph(self) -> None:
        while True:
            self.Nodes = self.Graph.GetNodes()
            cycles = nx.cycle_basis(self.Graph)
            polygons = [cycle for cycle in cycles if 1 < len(cycle) < self.PolyParam]
            positions = [[self.Graph.nodes[node]["pos"] for node in polygon] for polygon in polygons]
            areas = [cycle_area(pos) for pos in positions]

            polygons = [polygon for polygon, area in zip(polygons, areas) if area < self.AreaParam]
            positions = [pos for pos, area in zip(positions, areas) if area < self.AreaParam]
            if not polygons:
                break

            centers = [np.mean(pos, axis=0) for pos in positions]
            steps = [0.5 * (np.asarray(pos) - center) for pos, center in zip(positions, centers)]

            flat_nodes = [node for polygon in polygons for node in polygon]
            flat_steps = [step for polygon_steps in steps for step in polygon_steps]
            moves = {}
            for node, step in zip(flat_nodes, flat_steps):
                moves.setdefault(node, []).append(step)

            for node in self.Nodes:
                if node in moves:
                    self.Graph.nodes[node]["pos"] = self.Graph.nodes[node]["pos"] - np.asarray(moves[node][0])

            self.NodesToProcess = list(set(flat_nodes))
            self._update_topology(resolution=self.ClusteringResolution)

    def Update(self, AreaParam: float = 75.0, PolyParam: int = 10, ClusteringResolution: float = 1.0) -> None:
        self.AreaParam = AreaParam
        self.PolyParam = PolyParam
        self.ClusteringResolution = ClusteringResolution
        self._refine_graph()

    def GetOutput(self):
        return self.Graph
