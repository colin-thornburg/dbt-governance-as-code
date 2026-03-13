"""Generate REVIEW.md from governance configuration."""

from __future__ import annotations

from pathlib import Path

from dbt_governance.config import GovernanceConfig, Severity, load_config

RULE_CATEGORIES = (
    "naming",
    "structure",
    "testing",
    "documentation",
    "materialization",
    "style",
    "ai_review",
)

SEVERITY_HEADINGS = (
    (Severity.ERROR, "Always Check"),
    (Severity.WARNING, "Check with Warnings"),
    (Severity.INFO, "Optional Improvements"),
)


def _fallback_description(rule_name: str) -> str:
    return rule_name.replace("_", " ").strip().capitalize()


def _collect_rules_by_severity(config: GovernanceConfig) -> dict[Severity, list[str]]:
    grouped: dict[Severity, list[str]] = {
        Severity.ERROR: [],
        Severity.WARNING: [],
        Severity.INFO: [],
    }

    for category_name in RULE_CATEGORIES:
        category = getattr(config, category_name, None)
        if category is None or not getattr(category, "enabled", False):
            continue

        for rule_name, rule in category.rules.items():
            if not rule.enabled:
                continue
            description = (rule.description or "").strip() or _fallback_description(rule_name)
            grouped[rule.severity].append(description)

    for custom_rule in config.custom_rules:
        grouped[custom_rule.severity].append(custom_rule.description.strip() or custom_rule.name)

    return grouped


def generate_review_md(config: GovernanceConfig) -> str:
    """Render REVIEW.md content from a GovernanceConfig."""
    grouped_rules = _collect_rules_by_severity(config)

    lines = [
        "# dbt Governance Review Rules",
        "",
        "<!-- Auto-generated from .dbt-governance.yml by dbt-governance -->",
        "",
        f"Project: {config.project.name}",
        "",
        "Apply these standards during code review for changed dbt files. Prioritize errors, then warnings.",
    ]

    if config.project.description:
        lines.extend(["", config.project.description.strip()])

    for severity, heading in SEVERITY_HEADINGS:
        lines.extend(["", f"## {heading} ({severity.value.title()})"])
        items = grouped_rules[severity]
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("- None configured")

    lines.extend(["", "## Scope"])

    if config.global_config.exclude_paths:
        lines.append(f"- Skip these paths: {', '.join(config.global_config.exclude_paths)}")
    else:
        lines.append("- No excluded paths configured")

    if config.global_config.changed_files_only:
        lines.append("- Focus on changed files only")
    else:
        lines.append("- Review the full affected dbt surface, not only changed files")

    return "\n".join(lines) + "\n"


def write_review_md(
    config: GovernanceConfig | None = None,
    config_path: str | None = None,
    output_path: str | Path = "REVIEW.md",
) -> Path:
    """Write REVIEW.md to disk and return the output path."""
    resolved_config = config or load_config(config_path)
    path = Path(output_path)
    path.write_text(generate_review_md(resolved_config), encoding="utf-8")
    return path
