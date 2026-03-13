"""JSON report output for programmatic consumption."""

from __future__ import annotations

import json

from dbt_governance.scanner import ScanResult


def to_json(result: ScanResult, indent: int = 2) -> str:
    """Serialize a ScanResult to JSON."""
    return result.model_dump_json(indent=indent)


def write_json(result: ScanResult, path: str) -> None:
    """Write a ScanResult to a JSON file."""
    with open(path, "w") as f:
        f.write(to_json(result))
