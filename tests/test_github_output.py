"""Tests for GitHub Check output helpers."""

from __future__ import annotations

from dbt_governance.config import Severity
from dbt_governance.output.github import build_github_annotations, resolve_github_repository
from dbt_governance.output.sarif import to_sarif
from dbt_governance.rules.base import Violation
from dbt_governance.scanner import ScanResult, ScanSummary
import json


def test_resolve_github_repository_accepts_url(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "https://github.com/example-org/example-repo")

    assert resolve_github_repository() == "example-org/example-repo"


def test_build_github_annotations_uses_line_one_when_missing():
    result = ScanResult(
        project_name="Example",
        summary=ScanSummary(),
        violations=[
            Violation(
                rule_id="naming.staging_prefix",
                severity=Severity.ERROR,
                model_name="stg_orders",
                file_path="models/staging/stg_orders.sql",
                message="Example violation",
                suggestion="Fix it",
            )
        ],
    )

    annotations = build_github_annotations(result)

    assert len(annotations) == 1
    assert annotations[0]["path"] == "models/staging/stg_orders.sql"
    assert annotations[0]["start_line"] == 1
    assert annotations[0]["annotation_level"] == "failure"
    assert "Suggestion: Fix it" in annotations[0]["message"]


def test_sarif_stores_suggestion_in_properties_not_fixes():
    result = ScanResult(
        project_name="Example",
        summary=ScanSummary(),
        violations=[
            Violation(
                rule_id="naming.staging_prefix",
                severity=Severity.ERROR,
                model_name="stg_orders",
                file_path="models/staging/stg_orders.sql",
                message="Example violation",
                suggestion="Fix it",
            )
        ],
    )

    sarif = json.loads(to_sarif(result))
    sarif_result = sarif["runs"][0]["results"][0]

    assert "fixes" not in sarif_result
    assert sarif_result["properties"]["suggestion"] == "Fix it"
