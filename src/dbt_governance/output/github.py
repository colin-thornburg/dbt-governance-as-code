"""GitHub Check Run annotations for PR and commit validation."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from dbt_governance.rules.base import Violation
from dbt_governance.scanner import ScanResult

GITHUB_API_URL = "https://api.github.com"
ANNOTATION_BATCH_SIZE = 50

SEVERITY_TO_ANNOTATION_LEVEL = {
    "error": "failure",
    "warning": "warning",
    "info": "notice",
}


def resolve_github_repository() -> str:
    value = os.getenv("GITHUB_REPOSITORY", "").strip()
    if not value:
        raise EnvironmentError("Missing GITHUB_REPOSITORY. Set it to owner/repo or a GitHub repo URL.")

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        if path.count("/") >= 1:
            owner, repo = path.split("/", 1)
            return f"{owner}/{repo}"
        raise EnvironmentError(f"Unable to parse GITHUB_REPOSITORY URL: {value}")

    return value.removesuffix(".git")


def _build_annotation(violation: Violation) -> dict | None:
    if not violation.file_path:
        return None

    message = violation.message
    if violation.suggestion:
        message = f"{message}\n\nSuggestion: {violation.suggestion}"

    line_number = violation.line_number or 1
    return {
        "path": violation.file_path,
        "start_line": line_number,
        "end_line": line_number,
        "annotation_level": SEVERITY_TO_ANNOTATION_LEVEL[violation.severity.value],
        "title": violation.rule_id,
        "message": message[:65_000],
    }


def build_github_annotations(result: ScanResult) -> list[dict]:
    annotations = []
    for violation in result.violations:
        annotation = _build_annotation(violation)
        if annotation:
            annotations.append(annotation)
    return annotations


def _check_conclusion(result: ScanResult) -> str:
    if result.summary.errors > 0:
        return "failure"
    if result.summary.warnings > 0 or result.summary.info > 0:
        return "neutral"
    return "success"


def _check_summary(result: ScanResult) -> tuple[str, str]:
    summary = (
        f"Governance score: {result.summary.score:.1f}/100\n\n"
        f"- Errors: {result.summary.errors}\n"
        f"- Warnings: {result.summary.warnings}\n"
        f"- Info: {result.summary.info}\n"
        f"- Models scanned: {result.summary.models_scanned}\n"
        f"- Rules evaluated: {result.summary.rules_evaluated}\n"
    )

    if result.token_usage:
        summary += (
            "\nAI review:\n"
            f"- Provider: {result.token_usage.provider}\n"
            f"- Model: {result.token_usage.model}\n"
            f"- Models reviewed: {result.token_usage.models_reviewed}\n"
            f"- Estimated cost: ${result.token_usage.estimated_cost_usd:.5f}\n"
        )

    text_lines = []
    for violation in result.violations[:20]:
        text_lines.append(f"- [{violation.severity.value}] {violation.rule_id} — {violation.message}")
    omitted = max(0, len(result.violations) - 20)
    if omitted:
        text_lines.append(f"- ... {omitted} more violation(s) omitted from summary text")

    return summary, "\n".join(text_lines)


def publish_github_check(result: ScanResult, *, name: str = "dbt-governance") -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    head_sha = os.getenv("GITHUB_SHA", "").strip()
    repo = resolve_github_repository()

    if not token:
        raise EnvironmentError("Missing GITHUB_TOKEN.")
    if not head_sha:
        raise EnvironmentError("Missing GITHUB_SHA.")

    annotations = build_github_annotations(result)
    summary, text = _check_summary(result)
    timestamp = datetime.now(timezone.utc).isoformat()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base_payload = {
        "name": name,
        "head_sha": head_sha,
        "status": "completed",
        "completed_at": timestamp,
        "conclusion": _check_conclusion(result),
        "output": {
            "title": "dbt Governance Scan",
            "summary": summary,
            "text": text,
        },
    }

    with httpx.Client(base_url=GITHUB_API_URL, headers=headers, timeout=30.0) as client:
        first_batch = annotations[:ANNOTATION_BATCH_SIZE]
        payload = {
            **base_payload,
            "output": {
                **base_payload["output"],
                "annotations": first_batch,
            },
        }
        response = client.post(f"/repos/{repo}/check-runs", json=payload)
        response.raise_for_status()
        data = response.json()
        check_run_id = data["id"]

        remaining = annotations[ANNOTATION_BATCH_SIZE:]
        while remaining:
            batch = remaining[:ANNOTATION_BATCH_SIZE]
            remaining = remaining[ANNOTATION_BATCH_SIZE:]
            patch_payload = {
                "output": {
                    "title": "dbt Governance Scan",
                    "summary": summary,
                    "text": text,
                    "annotations": batch,
                }
            }
            patch_response = client.patch(f"/repos/{repo}/check-runs/{check_run_id}", json=patch_payload)
            patch_response.raise_for_status()

        return data.get("html_url", f"https://github.com/{repo}/commit/{head_sha}/checks")
