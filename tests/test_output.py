"""Tests for output formatters."""

from __future__ import annotations

import json
from pathlib import Path

from dbt_governance.output.sarif import to_sarif, write_sarif
from dbt_governance.scanner import run_scan

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_to_sarif_returns_valid_top_level_structure():
    result = run_scan(
        manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
        cloud_mode=False,
    )

    payload = json.loads(to_sarif(result, working_directory=str(FIXTURES_DIR)))

    assert payload["version"] == "2.1.0"
    assert payload["runs"]
    run = payload["runs"][0]
    assert run["tool"]["driver"]["name"] == "dbt-governance"
    assert run["results"]
    assert run["properties"]["projectName"] == result.project_name


def test_to_sarif_includes_rule_metadata_and_locations():
    result = run_scan(
        manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
        cloud_mode=False,
    )

    payload = json.loads(to_sarif(result))
    run = payload["runs"][0]
    first_result = run["results"][0]

    assert "ruleId" in first_result
    assert first_result["level"] in {"error", "warning", "note"}
    assert any(rule["id"] == first_result["ruleId"] for rule in run["tool"]["driver"]["rules"])

    located_results = [entry for entry in run["results"] if "locations" in entry]
    assert located_results
    assert "artifactLocation" in located_results[0]["locations"][0]["physicalLocation"]


def test_write_sarif_writes_file(tmp_path: Path):
    result = run_scan(
        manifest_path=str(FIXTURES_DIR / "sample_manifest.json"),
        cloud_mode=False,
    )
    output_path = tmp_path / "results.sarif"

    write_sarif(result, str(output_path), working_directory=str(tmp_path))

    assert output_path.exists()
    payload = json.loads(output_path.read_text())
    assert payload["runs"][0]["invocations"][0]["workingDirectory"]["uri"].startswith("file://")
