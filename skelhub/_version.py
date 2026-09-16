"""Resolve the SkelHub version from authoritative project metadata."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path
import tomllib


def get_version() -> str:
    """Return the version declared by ``pyproject.toml`` or installed metadata."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject_path.is_file():
        with pyproject_path.open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file).get("project", {})
        project_version = project.get("version")
        if isinstance(project_version, str) and project_version.strip():
            return project_version.strip()
        raise RuntimeError(f"Missing [project].version in {pyproject_path}")

    try:
        return distribution_version("skelhub")
    except PackageNotFoundError as exc:
        raise RuntimeError("Cannot determine the SkelHub version") from exc


__all__ = ["get_version"]
