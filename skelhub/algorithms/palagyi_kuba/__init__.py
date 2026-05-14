"""Palagyi-Kuba backend exports and registration."""

from skelhub.core import register_backend

from .backend import PalagyiKubaBackend
from .config import PalagyiKubaConfig

register_backend(PalagyiKubaBackend())

__all__ = ["PalagyiKubaBackend", "PalagyiKubaConfig"]
