"""Core framework exports."""

from .interfaces import SkeletonBackend
from .models import (
    EVALUATION_SCHEMA_VERSION,
    BettiNumbers,
    CountComparison,
    DistanceSummary,
    EvaluationResult,
    GeometryResult,
    GraphResult,
    SkeletonResult,
    ToleranceMatch,
    TopologyResult,
    VolumeData,
)
from .registry import get_backend, list_backends, register_backend

__all__ = [
    "EVALUATION_SCHEMA_VERSION",
    "BettiNumbers",
    "CountComparison",
    "DistanceSummary",
    "EvaluationResult",
    "GeometryResult",
    "GraphResult",
    "SkeletonBackend",
    "SkeletonResult",
    "ToleranceMatch",
    "TopologyResult",
    "VolumeData",
    "get_backend",
    "list_backends",
    "register_backend",
]
