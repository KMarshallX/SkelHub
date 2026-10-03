"""Core framework exports."""

from .interfaces import SkeletonBackend
from .models import (
    EVALUATION_SCHEMA_VERSION,
    FOREGROUND_EDT_NO_MASK_REASON,
    BettiNumbers,
    CountComparison,
    DistanceSummary,
    EvaluationResult,
    ForegroundEdtAgreement,
    ForegroundEdtSummary,
    ForegroundMaskInfo,
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
    "FOREGROUND_EDT_NO_MASK_REASON",
    "BettiNumbers",
    "CountComparison",
    "DistanceSummary",
    "EvaluationResult",
    "ForegroundEdtAgreement",
    "ForegroundEdtSummary",
    "ForegroundMaskInfo",
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
