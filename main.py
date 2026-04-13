"""Compatibility wrapper around the SkelHub framework CLI."""

from __future__ import annotations

import sys
from typing import Optional

from skelhub.cli.main import main as skelhub_main


def main(argv: Optional[list[str]] = None) -> int:
    """Route the legacy entrypoint through `skelhub run --algorithm mcp`."""
    args = ["run", "--algorithm", "mcp", *(sys.argv[1:] if argv is None else argv)]
    return skelhub_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
