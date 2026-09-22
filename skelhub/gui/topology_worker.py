"""Subprocess protocol for responsive TopoStats analysis."""
from __future__ import annotations

import argparse
import json
import sys

from .topology import analyze_path


def emit(kind: str, **values: object) -> None:
    """Send one complete JSON event to the GUI without output buffering."""
    print(json.dumps({"type": kind, **values}, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TopoStats in an isolated process.")
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    try:
        result = analyze_path(
            args.input,
            progress=lambda percent, message: emit("progress", percent=percent, message=message),
            summary=lambda values: emit("summary", values=values),
        )
        emit("result", values=result.as_report())
        return 0
    except Exception as exc:
        emit("error", message=f"{type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
