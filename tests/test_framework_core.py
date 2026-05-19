"""Framework-level unit tests."""

from __future__ import annotations

import numpy as np
import pytest

from skelhub.algorithms import Lee94Config
from skelhub.algorithms.mcp import MCPConfig
from skelhub.core import SkeletonResult, get_backend, list_backends


def test_registry_exposes_registered_backends() -> None:
    """The framework registry should expose the framework backends."""
    assert "mcp" in list_backends()
    assert get_backend("mcp").name == "mcp"
    assert "lee94" in list_backends()
    assert get_backend("lee94").name == "lee94"


def test_mcp_config_validation_rejects_bad_values() -> None:
    """Framework config validation should fail clearly for invalid MCP settings."""
    with pytest.raises(ValueError):
        MCPConfig(threshold_scale=0.0).validate()
    with pytest.raises(ValueError):
        MCPConfig(dilation_factor=0.0).validate()


def test_lee94_config_validation_accepts_default() -> None:
    """Lee94 config validation should accept the default threshold."""
    assert Lee94Config().validate().binarize_threshold == 0.5


def test_skeleton_result_keeps_framework_fields() -> None:
    """SkeletonResult should store shared framework-level fields explicitly."""
    result = SkeletonResult(
        algorithm_name="mcp",
        skeleton=np.zeros((2, 2, 2), dtype=np.uint8),
        input_metadata={"shape": (2, 2, 2)},
        runtime_stats={"wall_clock_seconds": 0.1},
        warnings=["test warning"],
        backend_metadata={"mcp": {"num_objects": 1}},
    )

    assert result.algorithm_name == "mcp"
    assert result.input_metadata["shape"] == (2, 2, 2)
    assert result.warnings == ["test warning"]
    assert result.backend_metadata["mcp"]["num_objects"] == 1
