"""Configuration for the L1-medial skeleton backend."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class L1SkeletonConfig:
    """Validated parameters for the Python-native L1 skeleton backend."""

    sample_count: int = 512
    initial_radius: float | None = None
    radius_growth: float = 1.5
    max_radius: float | None = None
    max_iterations: int = 80
    stop_error: float = 0.01
    repulsion_mu: float = 0.35
    repulsion_mu_min: float = 0.15
    random_seed: int = 0
    output_mode: str = "branches"
    use_density_weighting: bool = True
    use_recentering: bool = True
    eigen_threshold: float = 0.901
    branch_search_knn: int = 12
    accept_branch_size: int = 6
    add_accept_branch_size: int = 1
    branch_search_angle: float = 25.0
    branch_merge_distance: float = 0.08
    clean_near_branch_distance: float = 0.05
    curve_segment_length: float = 0.051

    def validate(self) -> "L1SkeletonConfig":
        """Validate config values and return self for chaining."""
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive.")
        if self.initial_radius is not None and self.initial_radius <= 0.0:
            raise ValueError("initial_radius must be positive when provided.")
        if self.radius_growth <= 1.0:
            raise ValueError("radius_growth must be greater than 1.0.")
        if self.max_radius is not None and self.max_radius <= 0.0:
            raise ValueError("max_radius must be positive when provided.")
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive.")
        if self.stop_error < 0.0:
            raise ValueError("stop_error must be non-negative.")
        if self.repulsion_mu < 0.0:
            raise ValueError("repulsion_mu must be non-negative.")
        if self.repulsion_mu_min < 0.0:
            raise ValueError("repulsion_mu_min must be non-negative.")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative.")
        if self.output_mode not in {"branches", "points"}:
            raise ValueError("output_mode must be either 'branches' or 'points'.")
        if not 0.0 <= self.eigen_threshold <= 1.0:
            raise ValueError("eigen_threshold must be between 0 and 1.")
        if self.branch_search_knn <= 0:
            raise ValueError("branch_search_knn must be positive.")
        if self.accept_branch_size <= 0:
            raise ValueError("accept_branch_size must be positive.")
        if self.add_accept_branch_size < 0:
            raise ValueError("add_accept_branch_size must be non-negative.")
        if not 0.0 < self.branch_search_angle <= 180.0:
            raise ValueError("branch_search_angle must be in (0, 180].")
        if self.branch_merge_distance < 0.0:
            raise ValueError("branch_merge_distance must be non-negative.")
        if self.clean_near_branch_distance < 0.0:
            raise ValueError("clean_near_branch_distance must be non-negative.")
        if self.curve_segment_length <= 0.0:
            raise ValueError("curve_segment_length must be positive.")
        return self
