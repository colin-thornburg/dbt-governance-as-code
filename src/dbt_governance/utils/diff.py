"""Git diff helpers for changed-files-only scans."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _candidate_base_refs() -> list[str]:
    refs: list[str] = []
    explicit = os.getenv("DBT_GOVERNANCE_BASE_REF")
    github = os.getenv("GITHUB_BASE_REF")
    gitlab = os.getenv("CI_MERGE_REQUEST_TARGET_BRANCH_NAME")

    for branch in [explicit, github, gitlab]:
        if not branch:
            continue
        refs.append(branch if "/" in branch else f"origin/{branch}")

    refs.extend(["origin/main", "origin/master"])
    return refs


def get_changed_files(project_dir: str | Path = ".") -> list[str]:
    """Return changed files from the current git checkout.

    Tries a PR-style diff against the detected base branch first, then falls back to
    the previous commit when no remote tracking branch is available.
    """
    project_dir = str(project_dir)

    for base_ref in _candidate_base_refs():
        result = _run_git(["diff", "--name-only", "--diff-filter=ACMR", f"{base_ref}...HEAD"], project_dir)
        if result.returncode == 0:
            return [Path(line.strip()).as_posix() for line in result.stdout.splitlines() if line.strip()]

    result = _run_git(["diff", "--name-only", "--diff-filter=ACMR", "HEAD~1...HEAD"], project_dir)
    if result.returncode == 0:
        return [Path(line.strip()).as_posix() for line in result.stdout.splitlines() if line.strip()]

    return []
