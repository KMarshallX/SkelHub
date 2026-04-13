"""Algorithm registry."""

from __future__ import annotations

from .interfaces import SkeletonBackend


_REGISTRY: dict[str, SkeletonBackend] = {}


def register_backend(backend: SkeletonBackend) -> None:
    """Register a backend by its unique algorithm name."""
    _REGISTRY[backend.name] = backend


def get_backend(name: str) -> SkeletonBackend:
    """Return a registered backend."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY)) or "none"
        raise ValueError(f"Unknown algorithm '{name}'. Available: {available}") from exc


def list_backends() -> list[str]:
    """Return registered backend names."""
    return sorted(_REGISTRY)
