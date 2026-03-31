"""SARIF output for GitHub Advanced Security and other code scanning tools."""

from __future__ import annotations

import json
from pathlib import Path

from dbt_governance import __version__
from dbt_governance.rules.base import get_all_rules
from dbt_governance.scanner import ScanResult

import dbt_governance.rules.documentation  # noqa: F401
import dbt_governance.rules.governance  # noqa: F401
import dbt_governance.rules.materialization  # noqa: F401
import dbt_governance.rules.migration  # noqa: F401
import dbt_governance.rules.naming  # noqa: F401
import dbt_governance.rules.reuse  # noqa: F401
import dbt_governance.rules.structure  # noqa: F401
import dbt_governance.rules.style  # noqa: F401
import dbt_governance.rules.testing  # noqa: F401

SARIF_SCHEMA_URL = "https://json.schemastore.org/sarif-2.1.0.json"

SEVERITY_TO_LEVEL = {
    "error": "error",
    "warning": "warning",
    "info": "note",
}


def _sarif_level(severity: str) -> str:
    return SEVERITY_TO_LEVEL.get(severity, "warning")


def _rule_descriptors(result: ScanResult) -> list[dict]:
    registry = get_all_rules()
    seen_rule_ids = {violation.rule_id for violation in result.violations}
    descriptors = []

    for rule_id in sorted(seen_rule_ids):
        rule_cls = registry.get(rule_id)
        description = rule_cls.description if rule_cls else rule_id
        default_level = _sarif_level(rule_cls.default_severity.value) if rule_cls else "warning"
        descriptors.append(
            {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": description},
                "help": {"text": description},
                "defaultConfiguration": {"level": default_level},
                "properties": {
                    "category": rule_id.split(".", 1)[0] if "." in rule_id else "other",
                },
            }
        )

    return descriptors


def _result_location(file_path: str, line_number: int | None) -> dict | None:
    if not file_path:
        return None

    region = {"startLine": line_number} if line_number else None
    physical_location = {
        "artifactLocation": {"uri": Path(file_path).as_posix()},
    }
    if region:
        physical_location["region"] = region

    return {"physicalLocation": physical_location}


def to_sarif(result: ScanResult, *, working_directory: str | None = None) -> str:
    """Serialize a ScanResult to SARIF 2.1.0 JSON."""
    sarif_results = []
    for violation in result.violations:
        entry = {
            "ruleId": violation.rule_id,
            "level": _sarif_level(violation.severity.value),
            "message": {"text": violation.message},
            "properties": {
                "severity": violation.severity.value,
                "modelName": violation.model_name,
                "aiGenerated": violation.ai_generated,
            },
        }
        if violation.suggestion:
            entry["properties"]["suggestion"] = violation.suggestion

        location = _result_location(violation.file_path, violation.line_number)
        if location:
            entry["locations"] = [location]

        sarif_results.append(entry)

    run = {
        "tool": {
            "driver": {
                "name": "dbt-governance",
                "version": __version__,
                "informationUri": "https://github.com/your-org/dbt-governance",
                "rules": _rule_descriptors(result),
            }
        },
        "results": sarif_results,
        "invocations": [
            {
                "executionSuccessful": True,
                "workingDirectory": {
                    "uri": Path(working_directory or ".").resolve().as_uri(),
                },
            }
        ],
        "properties": {
            "scanId": result.scan_id,
            "projectName": result.project_name,
            "isCloudMode": result.is_cloud_mode,
            "governanceScore": result.summary.score,
            "errors": result.summary.errors,
            "warnings": result.summary.warnings,
            "info": result.summary.info,
        },
    }

    sarif = {
        "$schema": SARIF_SCHEMA_URL,
        "version": "2.1.0",
        "runs": [run],
    }
    return json.dumps(sarif, indent=2)


def write_sarif(result: ScanResult, path: str, *, working_directory: str | None = None) -> None:
    """Write a ScanResult to a SARIF file."""
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write(to_sarif(result, working_directory=working_directory))
