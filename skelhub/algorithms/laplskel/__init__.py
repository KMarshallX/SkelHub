"""laplskel backend: Laplacian-flow skeletonisation adapted from upstream laplskel."""

from skelhub.core import register_backend

from .backend import LaplskelBackend
from .config import LaplskelConfig

register_backend(LaplskelBackend())

__all__ = ["LaplskelBackend", "LaplskelConfig"]
