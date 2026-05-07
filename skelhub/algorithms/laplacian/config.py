"""Configuration for the VascGraph Laplacian backend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LaplacianConfig:
    """Validated parameters for the graph-contraction skeletonization backend."""

    speed_param: float = 0.05
    dist_param: float = 0.5
    med_param: float = 0.5
    degree_threshold: float = 5.0
    sampling: float = 1.0
    clustering_r: float = 1.0
    stop_param: float = 0.001
    n_free_iteration: int = 0
    area_param: float = 50.0
    poly_param: int = 10
    graph_output: str | None = None

    def validate(self) -> "LaplacianConfig":
        """Validate config values and return self for chaining."""
        if self.speed_param <= 0.0:
            raise ValueError("speed_param must be positive.")
        if self.dist_param < 0.0:
            raise ValueError("dist_param must be non-negative.")
        if self.med_param < 0.0:
            raise ValueError("med_param must be non-negative.")
        if self.degree_threshold < 0.0:
            raise ValueError("degree_threshold must be non-negative.")
        if self.sampling <= 0.0:
            raise ValueError("sampling must be positive.")
        if self.clustering_r <= 0.0:
            raise ValueError("clustering_r must be positive.")
        if self.stop_param < 0.0:
            raise ValueError("stop_param must be non-negative.")
        if self.n_free_iteration < 0:
            raise ValueError("n_free_iteration must be non-negative.")
        if self.area_param < 0.0:
            raise ValueError("area_param must be non-negative.")
        if self.poly_param < 3:
            raise ValueError("poly_param must be at least 3.")
        return self
