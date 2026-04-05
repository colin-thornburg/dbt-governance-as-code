"""Generate .github/copilot-instructions.md from governance configuration.

GitHub Copilot Code Review reads .github/copilot-instructions.md from the base
branch to guide its PR feedback. Hard limit: Copilot Code Review only reads the
first 4,000 characters of the file. Content beyond that is silently ignored.

This generator produces a compact, imperative checklist that fits comfortably
within that limit while covering every enabled rule from the governance config.
"""

from __future__ import annotations

from pathlib import Path

from dbt_governance.config import GovernanceConfig, Severity, load_config
from dbt_governance.generators.review_md import _collect_rules_by_severity

_COPILOT_CHAR_LIMIT = 4000
_COPILOT_SAFE_LIMIT = 3900  # leave headroom for the truncation notice


def generate_copilot_md(config: GovernanceConfig) -> str:
    """Render .github/copilot-instructions.md content from a GovernanceConfig.

    The output is kept under 4,000 characters so GitHub Copilot Code Review
    reads the full file. Errors are marked blocking; warnings are suggestions.
    """
    grouped = _collect_rules_by_severity(config)

    lines: list[str] = [
        f"# dbt Governance — {config.project.name}",
        "",
        "<!-- Auto-generated from .dbt-governance.yml by dbt-governance -->",
        "<!-- Kept under 4,000 chars for GitHub Copilot Code Review compatibility -->",
        "",
        "When reviewing dbt pull requests, apply the rules below.",
        "Flag **errors** as blocking issues. Flag **warnings** as suggestions.",
        "",
    ]

    if config.project.description:
        lines.append(f"> {config.project.description.strip()}")
        lines.append("")

    if grouped[Severity.ERROR]:
        lines.append("## Must fix (errors — block merge)")
        lines.extend(f"- {rule}" for rule in grouped[Severity.ERROR])
        lines.append("")

    if grouped[Severity.WARNING]:
        lines.append("## Should fix (warnings — leave comment)")
        lines.extend(f"- {rule}" for rule in grouped[Severity.WARNING])
        lines.append("")

    if grouped[Severity.INFO]:
        lines.append("## Consider (improvements — optional)")
        lines.extend(f"- {rule}" for rule in grouped[Severity.INFO])
        lines.append("")

    lines.extend([
        "## Scope",
    ])
    if config.global_config.exclude_paths:
        lines.append(f"- Skip: {', '.join(config.global_config.exclude_paths)}")
    if config.global_config.changed_files_only:
        lines.append("- Focus on changed files only.")
    else:
        lines.append("- Review the full affected dbt surface, not only changed files.")

    content = "\n".join(lines) + "\n"

    if len(content) > _COPILOT_CHAR_LIMIT:
        content = (
            content[:_COPILOT_SAFE_LIMIT]
            + "\n\n<!-- Rules truncated to fit Copilot 4,000-character limit."
            " Run `dbt-governance generate copilot-md` to regenerate. -->\n"
        )

    return content


def write_copilot_md(
    config: GovernanceConfig | None = None,
    config_path: str | None = None,
    output_path: str | Path = ".github/copilot-instructions.md",
) -> Path:
    """Write .github/copilot-instructions.md to disk and return the output path."""
    resolved_config = config or load_config(config_path)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_copilot_md(resolved_config), encoding="utf-8")
    return path
