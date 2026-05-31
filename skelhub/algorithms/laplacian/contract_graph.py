"""Laplacian graph contraction extracted from VascGraph."""

from __future__ import annotations

import warnings

import networkx as nx
import numpy as np
import scipy as sp

from .base_graph import BaseGraph
from .progress import LaplacianProgress
from .tools import cycle_area_all, is_skeleton_nodes, numpy_fill


MAX_CONTRACTION_ITERATIONS = 750


class ContractGraph(BaseGraph):
    """Contract a dense foreground graph toward vessel centerlines."""

    def __init__(self, graph=None, freeze_ext: bool = False):
        super().__init__(label_ext=freeze_ext)
        self.Graph = graph
        self.freeze_ext = freeze_ext

    def _check_graph(self) -> None:
        nodes_to_remove = [node for node in self.Graph.GetNodes() if len(self.Graph.GetNeighbors(node)) == 0]
        self.Graph.remove_nodes_from(nodes_to_remove)

        if self.freeze_ext:
            ext_nodes = [node for node in self.Graph.GetNodes() if self.Graph.nodes[node].get("ext") == 1]
            graph_temp = self.Graph.copy()
            graph_temp.remove_nodes_from(ext_nodes)
            graph_temp.remove_nodes_from(
                [node for node in graph_temp.GetNodes() if len(graph_temp.GetNeighbors(node)) == 0]
            )
            self.Nodes = np.asarray(graph_temp.GetNodes(), dtype=int)
            self.Neighbors = [graph_temp.GetNeighbors(node) for node in self.Nodes]
        else:
            self.Nodes = np.asarray(self.Graph.GetNodes(), dtype=int)
            self.Neighbors = [self.Graph.GetNeighbors(node) for node in self.Nodes]

        self.NNodes = len(self.Nodes)
        self.NodesPos = np.asarray([self.Graph.nodes[node]["pos"] for node in self.Nodes], dtype=float)
        self.NeighborsPos = [
            np.asarray([self.Graph.nodes[neighbor]["pos"] for neighbor in neighbors], dtype=float)
            for neighbors in self.Neighbors
        ]
        self.MedialValues = np.asarray([self.Graph.nodes[node].get("r", 1.0) for node in self.Nodes], dtype=float)
        self.Degree = [len(neighbors) for neighbors in self.Neighbors]

        if self.DegreeThreshold is not None and self.NNodes:
            has_neighbors = np.asarray([len(neighbors) > 1 for neighbors in self.Neighbors], dtype=bool)
            angle_check = is_skeleton_nodes(self.NodesPos, self.NeighborsPos, self.DegreeThreshold)
            self.SkeletalMask = np.logical_and(has_neighbors, angle_check)
        else:
            self.SkeletalMask = np.zeros(self.NNodes, dtype=bool)

        self.NodesToProcess = self.Nodes[~self.SkeletalMask]
        self.PosToProcess = self.NodesPos[~self.SkeletalMask]
        self.SkeletalNodes = self.Nodes[self.SkeletalMask]

    def _check_iter(self):
        cycles = nx.cycle_basis(self.Graph)
        area = 0.0
        for length in range(3, 10):
            polygons = [cycle for cycle in cycles if len(cycle) == length]
            if polygons:
                pos = np.asarray([[self.Graph.nodes[node]["pos"] for node in polygon] for polygon in polygons])
                area += float(np.sum(cycle_area_all(pos)))
        return area > self.AreaThreshold, area

    def _dist_matrix(self):
        neighbor_pos, mask = numpy_fill(self.NeighborsPos, self.Degree, 3)
        distances = np.linalg.norm(self.NodesPos[:, None, :] - neighbor_pos, axis=2) * mask
        totals = np.sum(distances, axis=1)
        totals[totals == 0] = 1.0
        return distances / totals[:, None], mask

    def _med_matrix(self, neighbors_mat, mask, node_indices):
        neighbor_indices = [node_indices[int(node)] for node in neighbors_mat[mask].astype(int)]
        med = np.zeros_like(neighbors_mat, dtype=float)
        med[mask] = self.MedialValues[neighbor_indices]
        totals = np.sum(med, axis=1)
        totals[totals == 0] = 1.0
        return med / totals[:, None]

    def _apply_contraction(self) -> None:
        if self.NNodes == 0 or not any(self.Degree):
            return

        ordered_indices = np.arange(self.NNodes, dtype=int)
        node_indices = {int(node): index for index, node in enumerate(self.Nodes)}
        neighbors_mat, neighbor_mask = numpy_fill(self.Neighbors, self.Degree)
        dist_mat, dist_mask = self._dist_matrix()
        med_mat = self._med_matrix(neighbors_mat, neighbor_mask, node_indices)

        dist_values = dist_mat[dist_mask]
        med_values = med_mat[neighbor_mask]
        speed_values = (
            (~self.SkeletalMask) * self.SpeedParam
            + self.SkeletalMask * self.AlleviateParam * self.SpeedParam
        )

        matrix = sp.sparse.lil_matrix((self.NNodes * 3, self.NNodes))
        row_indices = np.zeros_like(neighbors_mat, dtype=int) + ordered_indices[:, None]
        neighbor_rows = row_indices[neighbor_mask].astype(int)
        neighbor_cols = [node_indices[int(node)] for node in neighbors_mat[neighbor_mask].astype(int)]

        matrix[neighbor_rows.tolist(), neighbor_cols] = dist_values * self.DistParam
        matrix[ordered_indices, ordered_indices] = -1.0 * self.DistParam

        matrix[(neighbor_rows + self.NNodes).tolist(), neighbor_cols] = med_values * self.MedParam
        matrix[ordered_indices + self.NNodes, ordered_indices] = -1.0 * self.MedParam

        speed_rows = ordered_indices + 2 * self.NNodes
        matrix[speed_rows, ordered_indices] = speed_values
        matrix = matrix.tocoo()

        rhs = np.vstack(
            [
                np.zeros_like(self.NodesPos),
                np.zeros_like(self.NodesPos),
                self.NodesPos * np.asarray([speed_values, speed_values, speed_values]).T,
            ]
        )

        new_pos = np.asarray(
            [
                sp.sparse.linalg.lsqr(matrix, rhs[:, axis], atol=1e-6, btol=1e-6)[0]
                for axis in range(3)
            ]
        ).T
        for index, node in enumerate(self.Nodes):
            self.Graph.nodes[int(node)]["pos"] = new_pos[index]

    def _contract_graph(self, progress: LaplacianProgress | None = None) -> None:
        self.Iteration = 1
        self.max_iterations_reached = False
        check = True
        last_area = float(getattr(self.Graph, "Area", 0.0))
        while check:
            if self.Iteration == 1:
                self.AreaThreshold = float(getattr(self.Graph, "Area", 0.0)) * self.StopParam

            self._check_graph()
            self._apply_contraction()
            self._update_topology(resolution=self.ClusteringResolution)

            if self.Iteration >= self.NFreeIteration:
                check, last_area = self._check_iter()
                self.Graph.Area = last_area
            if progress:
                progress.detail(
                    f"iteration={self.Iteration}, nodes={self.Graph.number_of_nodes()}, "
                    f"cycle_area={last_area:.3f}, target<={self.AreaThreshold:.3f}"
                )
            self.Iteration += 1

            if self.Iteration > MAX_CONTRACTION_ITERATIONS:
                self.max_iterations_reached = True
                warnings.warn(
                    "Laplacian contraction reached 750 iterations; using the latest contracted graph.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                break

        self.final_cycle_area = last_area

    def Update(
        self,
        DistParam: float = 1.0,
        MedParam: float = 1.0,
        SpeedParam: float = 0.1,
        DegreeThreshold: float | None = None,
        NFreeIteration: int = 1,
        ClusteringResolution: float = 1.0,
        StopParam: float = 0.01,
        Alleviate_param: float = 10.0,
        progress: LaplacianProgress | None = None,
    ) -> None:
        self.DistParam = DistParam
        self.MedParam = MedParam
        self.SpeedParam = SpeedParam
        self.DegreeThreshold = DegreeThreshold
        self.NFreeIteration = NFreeIteration
        self.ClusteringResolution = ClusteringResolution
        self.StopParam = StopParam
        self.AlleviateParam = Alleviate_param
        self._contract_graph(progress=progress)

    def GetOutput(self):
        return self.Graph
