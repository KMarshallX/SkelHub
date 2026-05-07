"""Laplacian backend exports and registration."""

from skelhub.core import register_backend

from .backend import LaplacianBackend
from .config import LaplacianConfig

register_backend(LaplacianBackend())

__all__ = ["LaplacianBackend", "LaplacianConfig"]
