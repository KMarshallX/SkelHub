"""Dense foreground-mask graph generation for the Laplacian backend."""

from __future__ import annotations

import numpy as np
import scipy.ndimage as ndi

from .graph import GeometricGraph
from .tools import cumulative_small_cycle_area, distance_map_3d, fix_graph


class GenerateGraph:
    """Generate a dense geometric graph from a 3D binary foreground mask."""

    def __init__(self, label: np.ndarray, distance_map: np.ndarray | None = None, label_ext: bool = False):
        self.Label = np.asarray(label) > 0
        self.label_ext = label_ext
        self.Shape = self.Label.shape
        self.Length = int(np.prod(self.Shape))
        self.Area = 0.0
        self.DistMap = distance_map

    def _calculate_dist_map(self) -> None:
        if self.DistMap is None:
            self.DistMap = distance_map_3d(self.Label)

    def _assign_dist_map_to_graph(self) -> None:
        for node in self.Graph.GetNodes():
            pos = tuple(np.round(self.Graph.nodes[node]["pos"]).astype(int))
            if all(0 <= pos[axis] < self.Shape[axis] for axis in range(3)):
                distance = float(self.DistMap[pos])
                self.Graph.nodes[node]["r"] = max(distance, 1.0)
            else:
                self.Graph.nodes[node]["r"] = 1.0

    def _voxel_positions(self, label: np.ndarray) -> np.ndarray:
        return np.argwhere(label.astype(bool)).astype(float)

    def _grid_connections(self, label: np.ndarray):
        shape = label.shape
        array = (np.arange(np.prod(shape), dtype=int).reshape(shape) + 1) * label.astype(int)
        voxel_indices = array[label.astype(bool)]

        connections = []
        for axis in range(3):
            left = [slice(None)] * 3
            right = [slice(None)] * 3
            left[axis] = slice(0, -1)
            right[axis] = slice(1, None)
            pairs = np.stack([array[tuple(left)].ravel(), array[tuple(right)].ravel()], axis=1)
            pairs = pairs[np.all(pairs > 0, axis=1)]
            connections.extend((int(u), int(v)) for u, v in pairs)
        return voxel_indices, connections

    def _generate_grid_graph_from_label(self) -> None:
        if self.Sampling is not None:
            scale = (1.0 / self.Sampling, 1.0 / self.Sampling, 1.0 / self.Sampling)
            label = ndi.zoom(self.Label.astype(int), scale, order=0) > 0
        else:
            label = self.Label

        voxel_positions = self._voxel_positions(label)
        voxel_indices, connections = self._grid_connections(label)

        self.Graph = GeometricGraph()
        self.Graph.add_nodes_from(int(index) for index in voxel_indices)
        for index, pos in zip(voxel_indices, voxel_positions):
            self.Graph.nodes[int(index)]["pos"] = pos
        self.Graph.add_edges_from(connections)

        if self.label_ext:
            max_pos = np.asarray(label.shape) - 1
            for node in self.Graph.GetNodes():
                pos = self.Graph.nodes[node]["pos"]
                self.Graph.nodes[node]["ext"] = int(np.any((pos == 0) | (pos == max_pos)))

        if self.Sampling is not None:
            for node in self.Graph.GetNodes():
                self.Graph.nodes[node]["pos"] = self.Graph.nodes[node]["pos"] * self.Sampling

    def UpdateGridGraph(self, Sampling=None) -> None:
        self.Sampling = float(Sampling) if Sampling is not None else None
        self._generate_grid_graph_from_label()

    def GetOutput(self):
        self._calculate_dist_map()
        self._assign_dist_map_to_graph()
        self.Graph = fix_graph(self.Graph)
        self.Area = cumulative_small_cycle_area(self.Graph)
        self.Graph.Area = self.Area
        return self.Graph
