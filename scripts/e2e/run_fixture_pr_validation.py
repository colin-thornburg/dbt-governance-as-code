"""Create disposable fixture PRs and report whether governance automation behaved correctly."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({' '.join(cmd)}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout.strip()


def clone_repo(repo: str, destination: Path) -> Path:
    run(["gh", "repo", "clone", repo, str(destination)])
    return destination


def write_good_scenario(repo_dir: Path) -> None:
    config_path = repo_dir / ".dbt-governance.yml"
    existing = config_path.read_text()
    marker = "# e2e-good-touch"
    if marker not in existing:
        config_path.write_text(existing.rstrip() + f"\n{marker}\n")


def write_bad_scenario(repo_dir: Path) -> None:
    bad_model = repo_dir / "models" / "staging" / "e2e_bad_orders.sql"
    bad_model.parent.mkdir(parents=True, exist_ok=True)
    bad_model.write_text(
        """with raw_data as (
    select *
    from prod.orders
)
select *
from raw_data
""",
        encoding="utf-8",
    )


def create_pr(repo: str, repo_dir: Path, branch: str, base_branch: str, title: str, body: str) -> dict:
    run(["git", "checkout", base_branch], cwd=repo_dir)
    run(["git", "pull", "--ff-only", "origin", base_branch], cwd=repo_dir)
    run(["git", "checkout", "-b", branch], cwd=repo_dir)
    run(["git", "add", "-A"], cwd=repo_dir)
    run(["git", "commit", "-m", title], cwd=repo_dir)
    run(["git", "push", "-u", "origin", branch], cwd=repo_dir)

    pr_url = run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--base",
            base_branch,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=repo_dir,
    )
    pr_data = json.loads(run(["gh", "pr", "view", pr_url, "--repo", repo, "--json", "number,url,headRefName,headRefOid"]))
    return pr_data


def poll_check_runs(repo: str, head_sha: str, timeout_seconds: int, poll_seconds: int) -> list[dict]:
    started = time.time()
    while True:
        payload = json.loads(run(["gh", "api", f"repos/{repo}/commits/{head_sha}/check-runs"]))
        checks = payload.get("check_runs", [])
        if checks and all(check.get("status") == "completed" for check in checks):
            return checks

        if time.time() - started > timeout_seconds:
            return checks

        time.sleep(poll_seconds)


def collect_pr_comments(repo: str, number: int) -> dict:
    issue_comments = json.loads(run(["gh", "api", f"repos/{repo}/issues/{number}/comments"]))
    review_comments = json.loads(run(["gh", "api", f"repos/{repo}/pulls/{number}/comments"]))
    return {
        "issue_comments": issue_comments,
        "review_comments": review_comments,
    }


def write_report(output_dir: Path, report: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    report["generated_at"] = timestamp

    json_path = output_dir / "fixture-pr-validation.json"
    md_path = output_dir / "fixture-pr-validation.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Fixture PR Validation Report",
        "",
        f"Generated at: `{timestamp}`",
        "",
        f"Repository: `{report['repo']}`",
        "",
    ]

    for scenario in report["scenarios"]:
        lines.extend(
            [
                f"## {scenario['name'].title()} Scenario",
                "",
                f"- PR: {scenario['url']}",
                f"- Branch: `{scenario['branch']}`",
                f"- Check runs observed: {len(scenario['checks'])}",
                f"- Review comments observed: {len(scenario['comments']['review_comments'])}",
                f"- Issue comments observed: {len(scenario['comments']['issue_comments'])}",
                "",
            ]
        )
        if scenario["checks"]:
            lines.append("| Check | Conclusion |")
            lines.append("|---|---|")
            for check in scenario["checks"]:
                lines.append(f"| {check['name']} | {check.get('conclusion', 'pending')} |")
            lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Open fixture PRs and validate governance automation.")
    parser.add_argument("--repo", required=True, help="GitHub fixture repo in owner/name format.")
    parser.add_argument("--base-branch", default="main", help="Base branch to open fixture PRs against.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/e2e",
        help="Directory to write the markdown/json validation report into.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=900, help="How long to wait for PR checks.")
    parser.add_argument("--poll-seconds", type=int, default=15, help="Polling interval for PR checks.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the local validation clone after reporting. Generated PRs remain open.",
    )
    args = parser.parse_args()

    temp_dir = Path(tempfile.mkdtemp(prefix="dbt-governance-e2e-"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    scenarios = []
    for name, writer in [("good", write_good_scenario), ("bad", write_bad_scenario)]:
        scenario_dir = clone_repo(args.repo, temp_dir / f"fixture-{name}")
        writer(scenario_dir)
        branch = f"e2e/{name}-{run_id}"
        title = f"e2e: {name} fixture validation"
        body = (
            "Automated PR created by dbt-governance fixture validation.\n\n"
            f"Scenario: {name}\n"
            "- good: harmless config touch expected to pass\n"
            "- bad: intentionally broken staging model expected to fail"
        )
        pr_data = create_pr(args.repo, scenario_dir, branch, args.base_branch, title, body)
        checks = poll_check_runs(args.repo, pr_data["headRefOid"], args.timeout_seconds, args.poll_seconds)
        comments = collect_pr_comments(args.repo, pr_data["number"])
        scenarios.append(
            {
                "name": name,
                "branch": branch,
                "url": pr_data["url"],
                "number": pr_data["number"],
                "checks": checks,
                "comments": comments,
            }
        )

    report = {
        "repo": args.repo,
        "scenarios": scenarios,
    }
    write_report(Path(args.output_dir), report)

    if args.cleanup:
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()
