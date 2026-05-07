"""Topology update helpers for the Laplacian graph-contraction backend."""

from __future__ import annotations

import numpy as np

from .tools import assign_to_clusters


class BaseGraph:
    """Shared topology surgery used by contraction and refinement."""

    def __init__(self, label_ext: bool = False):
        self.label_ext = label_ext

    def _update_topology(self, resolution: float = 1.0) -> None:
        """Cluster moving nodes and replace clusters with centroid nodes."""
        pos = np.asarray([self.Graph.nodes[node]["pos"] for node in self.NodesToProcess], dtype=float)
        if pos.shape[0] == 0:
            return

        centroids, _, clusters = assign_to_clusters(pos, resolution=resolution)
        clusters = [[self.NodesToProcess[index] for index in cluster] for cluster in clusters]
        if centroids:
            self._connection_surgery(centroids=centroids, clusters=clusters)

    def _connection_surgery(self, clusters, centroids=None) -> None:
        def neighbors_of_neighbors(graph, clusters):
            out = []
            for cluster in clusters:
                cluster_nodes = list(cluster)
                neighbors = [item for node in cluster_nodes for item in graph.GetNeighbors(node)]
                out.append(list(set(neighbors).difference(set(cluster_nodes))))
            return out

        current_nodes = self.Graph.GetNodes()
        next_node = max(current_nodes) + 1 if current_nodes else 0
        new_nodes = list(range(next_node, next_node + len(clusters)))
        self.Graph.add_nodes_from(new_nodes)

        if centroids is None:
            centroids = [
                np.mean(np.asarray([self.Graph.nodes[node]["pos"] for node in cluster]), axis=0)
                for cluster in clusters
            ]

        for node, centroid in zip(new_nodes, centroids):
            self.Graph.nodes[node]["pos"] = np.asarray(centroid, dtype=float)

        for attr in ("d", "r"):
            try:
                new_values = [max(self.Graph.nodes[node][attr] for node in cluster) for cluster in clusters]
            except KeyError:
                continue
            for node, value in zip(new_nodes, new_values):
                self.Graph.nodes[node][attr] = value

        if self.label_ext:
            for node in new_nodes:
                self.Graph.nodes[node]["ext"] = 0

        clustered_nodes = [node for cluster in clusters for node in cluster]
        void_nodes = list(set(self.Nodes).difference(set(clustered_nodes)))
        nbrs_of_nbrs = neighbors_of_neighbors(self.Graph, clusters)

        self.Graph.add_edges_from(
            [[new_node, neighbor] for new_node, neighbors in zip(new_nodes, nbrs_of_nbrs) for neighbor in neighbors]
        )

        nodes_to_keep = set(new_nodes).union(set(void_nodes))
        other_nodes = list(set(self.Nodes).difference(nodes_to_keep))
        old_to_new = {node: 0 for node in other_nodes}
        for new_node, cluster in zip(new_nodes, clusters):
            for old_node in cluster:
                old_to_new[old_node] = new_node

        new_connections = []
        for new_node, neighbors in zip(new_nodes, nbrs_of_nbrs):
            for neighbor in neighbors:
                if neighbor in old_to_new:
                    new_connections.append([new_node, old_to_new[neighbor]])
        self.Graph.add_edges_from(new_connections)
        self.Graph.remove_nodes_from(other_nodes)
