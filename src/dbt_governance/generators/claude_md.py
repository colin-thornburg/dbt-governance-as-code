"""Generate CLAUDE.md project context from governance configuration."""

from __future__ import annotations

from pathlib import Path

from dbt_governance.config import GovernanceConfig, load_config

DEFAULT_NAMING_PATTERNS = {
    "staging_prefix": "stg_{source}__{entity}",
    "intermediate_prefix": "int_{entity}_{verb}",
}

DEFAULT_MART_PATTERNS = {
    "facts": "fct_{entity}",
    "dimensions": "dim_{entity}",
    "other": "{entity}",
}


def _append_if_present(lines: list[str], label: str, value: str | None) -> None:
    if value:
        lines.append(f"- {label}: {value}")


def generate_claude_md(config: GovernanceConfig) -> str:
    """Render CLAUDE.md content from a GovernanceConfig."""
    lines = [
        f"# dbt Project: {config.project.name}",
        "",
        "<!-- Auto-generated from .dbt-governance.yml by dbt-governance -->",
        "",
    ]

    if config.project.description:
        lines.append(config.project.description.strip())
        lines.append("")

    lines.extend(
        [
            "## Review Context",
            "- This repository uses dbt governance as code. Apply the standards below when reviewing SQL, YAML, and model structure changes.",
        ]
    )

    if config.dbt_cloud.enabled:
        lines.append(
            "- Primary metadata source: "
            f"dbt Cloud environment `{config.dbt_cloud.environment_id}` "
            f"using `{config.dbt_cloud.state_type}` state."
        )
    else:
        lines.append("- Primary metadata source: local `manifest.json` fallback mode.")

    lines.extend(["", "## Architecture Expectations"])
    if config.structure.enabled:
        lines.append("- Preferred layer progression: staging -> intermediate -> marts.")
        directories = config.structure.rules.get("model_directories_match_layers")
        if directories:
            for layer, path in (directories.model_extra or {}).get("directories", {}).items():
                lines.append(f"- {layer.title()} models belong under `{path}`.")
    else:
        lines.append("- No structure rules are currently enabled.")

    lines.extend(["", "## Naming Conventions"])
    if config.naming.enabled:
        naming_rules = config.naming.rules
        staging = naming_rules.get("staging_prefix")
        intermediate = naming_rules.get("intermediate_prefix")
        marts = naming_rules.get("marts_prefix")
        _append_if_present(
            lines,
            "Staging",
            (staging.model_extra or {}).get("pattern") if staging else DEFAULT_NAMING_PATTERNS["staging_prefix"],
        )
        _append_if_present(
            lines,
            "Intermediate",
            (intermediate.model_extra or {}).get("pattern")
            if intermediate
            else DEFAULT_NAMING_PATTERNS["intermediate_prefix"],
        )
        if marts:
            patterns = (marts.model_extra or {}).get("patterns")
            if isinstance(patterns, dict):
                pattern_text = ", ".join(f"{name}={pattern}" for name, pattern in patterns.items())
                _append_if_present(lines, "Marts", pattern_text)
        else:
            pattern_text = ", ".join(f"{name}={pattern}" for name, pattern in DEFAULT_MART_PATTERNS.items())
            _append_if_present(lines, "Marts", pattern_text)
    else:
        lines.append("- No naming rules are currently enabled.")

    lines.extend(["", "## Enforcement Notes"])
    lines.append(f"- CI fails on `{config.global_config.fail_on.value}` severity or higher.")
    if config.global_config.exclude_paths:
        lines.append(
            "- Ignore these paths during review unless explicitly requested: "
            f"{', '.join(config.global_config.exclude_paths)}"
        )
    if config.testing.enabled:
        lines.append("- Preserve model tests, especially primary key, coverage, and source freshness expectations.")
    if config.documentation.enabled:
        lines.append("- Maintain descriptions in schema YAML for the required layers and sources.")
    if config.materialization.enabled:
        lines.append("- Check materialization choices and incremental safeguards before approving model changes.")
    if config.style.enabled:
        lines.append("- Enforce dbt-specific SQL style, including `ref()` placement and avoidance of hardcoded schemas.")
    if config.ai_review.enabled:
        provider_models = []
        for provider in config.ai_review.enabled_providers():
            provider_config = config.ai_review.get_provider_config(provider)
            if provider_config.models:
                provider_models.append(f"{provider.value}: {', '.join(provider_config.models)}")
        if provider_models:
            lines.append(f"- AI semantic review providers enabled: {'; '.join(provider_models)}.")
        else:
            lines.append(f"- AI semantic review is enabled with primary model `{config.ai_review.model}`.")

    return "\n".join(lines) + "\n"


def write_claude_md(
    config: GovernanceConfig | None = None,
    config_path: str | None = None,
    output_path: str | Path = "CLAUDE.md",
) -> Path:
    """Write CLAUDE.md to disk and return the output path."""
    resolved_config = config or load_config(config_path)
    path = Path(output_path)
    path.write_text(generate_claude_md(resolved_config), encoding="utf-8")
    return path
