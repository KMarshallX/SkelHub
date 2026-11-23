"""Disjoint-set data structure"""

import numpy as np


class UnionFind:
    """Disjoint-set data structure with path compression for O(1) edge collapses."""

    def __init__(self, n):
        self.parent = np.arange(n)

    def find(self, i):
        # Path compression: update parent pointers recursively
        path = []
        while self.parent[i] != i:
            path.append(i)
            i = self.parent[i]
        for node in path:
            self.parent[node] = i
        return i

    def union(self, i, j):
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i != root_j:
            self.parent[root_j] = root_i
            return True, root_i, root_j
        return False, root_i, root_j
