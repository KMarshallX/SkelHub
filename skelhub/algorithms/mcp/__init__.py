"""MCP backend exports and registration."""

from skelhub.core import register_backend

from .backend import MCPBackend
from .config import MCPConfig

register_backend(MCPBackend())

__all__ = ["MCPBackend", "MCPConfig"]
