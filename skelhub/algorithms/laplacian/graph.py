"""Small NetworkX 3.x-compatible geometric graph used by the Laplacian backend."""

from __future__ import annotations

import networkx as nx
import numpy as np


class GeometricGraph(nx.Graph):
    """Undirected graph with VascGraph-style geometry convenience methods."""

    def __init__(self, nodes_pos=None, edges=None, radii=None, data=None, types=None):
        super().__init__(data=data)
        self.Area = 0
        self.info = {}
        self.set_geom_graph(nodes_pos=nodes_pos, edges=edges, radii=radii, types=types)

    @property
    def node(self):
        """Compatibility alias for old NetworkX ``Graph.node`` access."""
        return self._node

    def set_geom_graph(self, nodes_pos=None, edges=None, radii=None, types=None) -> None:
        """Populate the graph with optional positions, edges, radii, and types."""
        if nodes_pos is not None:
            self.add_nodes_from(range(len(nodes_pos)))
            self.set_nodes_pos(nodes_pos)
        if edges is not None:
            self.add_edges_from(edges)
        if radii is not None:
            self.set_radii(radii)
        elif self.number_of_nodes():
            self.set_radii([1] * self.number_of_nodes())
        if types is not None:
            self.set_types(types)
        elif self.number_of_nodes():
            self.set_types([1] * self.number_of_nodes())

    def GetNodes(self):
        """Return graph node ids as a list."""
        return list(self.nodes)

    def GetEdges(self):
        """Return graph edges as a list."""
        return list(self.edges)

    def GetNodesPos(self):
        """Return node positions in node iteration order."""
        return [self.nodes[node]["pos"] for node in self.GetNodes()]

    def set_nodes_pos(self, nodes_pos) -> None:
        for node, pos in zip(self.GetNodes(), nodes_pos):
            self.nodes[node]["pos"] = np.asarray(pos, dtype=float)

    SetNodesPos = set_nodes_pos

    def set_radii(self, radii) -> None:
        for node, radius in zip(self.GetNodes(), radii):
            self.nodes[node]["r"] = float(radius)

    SetRadii = set_radii

    def set_types(self, types) -> None:
        for node, node_type in zip(self.GetNodes(), types):
            self.nodes[node]["type"] = node_type

    SetTypes = set_types

    def GetRadii(self):
        """Return node radii or diameters where available."""
        values = []
        for node in self.GetNodes():
            attrs = self.nodes[node]
            values.append(attrs.get("d", attrs.get("r", 1.0)))
        return values

    def GetNeighbors(self, node=None):
        """Return neighbors for one node or for all nodes."""
        if node is None:
            return [list(self.neighbors(item)) for item in self.GetNodes()]
        return list(self.neighbors(node))

    def GetNodesDegree(self, nbunch=None, weight=None):
        """Return degrees as a list."""
        return [degree for _, degree in self.degree(nbunch=nbunch, weight=weight)]

    def copy(self, as_view=False):
        """Return a copy preserving this subclass and custom attributes."""
        copied = super().copy(as_view=as_view)
        if as_view:
            return copied
        copied.Area = getattr(self, "Area", 0)
        copied.info = dict(getattr(self, "info", {}))
        return copied
