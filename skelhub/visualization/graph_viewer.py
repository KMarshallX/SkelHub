"""Compatibility facade for the modular PyVista graph viewer implementation."""

from __future__ import annotations

from .constants import *  # noqa: F403
from .models import *  # noqa: F403
from .loading import *  # noqa: F403
from .session import *  # noqa: F403
from .scene import *  # noqa: F403
from .layout import *  # noqa: F403
from .camera import *  # noqa: F403
from .controls import *  # noqa: F403
from .interaction import *  # noqa: F403
from .launcher import *  # noqa: F403
from . import _graph_viewer_impl as _impl


def _exported_runtime_names() -> tuple[str, ...]:
    """Return all legacy runtime names, including private helper names."""
    return tuple(name for name in dir(_impl) if not (name.startswith("__") and name.endswith("__")))


globals().update({name: getattr(_impl, name) for name in _exported_runtime_names()})

__all__ = _exported_runtime_names()
