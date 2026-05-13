"""L1-medial skeleton backend exports and registration."""

from skelhub.core import register_backend

from .backend import L1SkeletonBackend
from .config import L1SkeletonConfig

register_backend(L1SkeletonBackend())

__all__ = ["L1SkeletonBackend", "L1SkeletonConfig"]
