"""Flux backend exports and registration."""

from skelhub.core import register_backend

from .backend import FluxBackend
from .config import FluxConfig

register_backend(FluxBackend())

__all__ = ["FluxBackend", "FluxConfig"]
