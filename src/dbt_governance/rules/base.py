"""Base rule class, violation model, rule context, and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from dbt_governance.cloud.models import ManifestData
from dbt_governance.config import GovernanceConfig, Severity


class Violation(BaseModel):
    rule_id: str
    severity: Severity
    model_name: str
    file_path: str = ""
    line_number: int | None = None
    message: str
    suggestion: str | None = None
    ai_generated: bool = False


class RuleContext(BaseModel):
    """Everything a rule needs to evaluate — assembled by the scanner."""

    manifest_data: ManifestData
    project_config: dict = Field(default_factory=dict)
    schema_files: dict[str, dict] = Field(default_factory=dict)
    sql_files: dict[str, str] = Field(default_factory=dict)
    governance_config: GovernanceConfig = Field(default_factory=GovernanceConfig)
    changed_files: list[str] | None = None
    is_cloud_mode: bool = False

    model_config = {"arbitrary_types_allowed": True}


class BaseRule(ABC):
    """Base class for all governance rules."""

    rule_id: str = ""
    category: str = ""
    description: str = ""
    default_severity: Severity = Severity.WARNING

    @abstractmethod
    def evaluate(self, context: RuleContext) -> list[Violation]:
        """Evaluate this rule against the provided context and return violations."""
        ...

    def get_severity(self, config: GovernanceConfig) -> Severity:
        """Get effective severity from config, falling back to default."""
        parts = self.rule_id.split(".")
        if len(parts) == 2:
            category, rule_name = parts
            return config.get_rule_severity(category, rule_name)
        return self.default_severity

    def is_enabled(self, config: GovernanceConfig) -> bool:
        """Check if this rule is enabled in the config."""
        parts = self.rule_id.split(".")
        if len(parts) == 2:
            category, rule_name = parts
            return config.is_rule_enabled(category, rule_name)
        return True

    def get_rule_config_value(self, config: GovernanceConfig, key: str, default: Any = None) -> Any:
        """Get a custom config value from the rule's config block."""
        parts = self.rule_id.split(".")
        if len(parts) != 2:
            return default
        category, rule_name = parts
        category_config = getattr(config, category, None)
        if category_config and hasattr(category_config, "rules"):
            rule = category_config.rules.get(rule_name)
            if rule:
                extra = rule.model_extra or {}
                return extra.get(key, default)
        return default


# Global rule registry
_rule_registry: dict[str, type[BaseRule]] = {}


def register_rule(cls: type[BaseRule]) -> type[BaseRule]:
    """Decorator to register a rule class in the global registry."""
    _rule_registry[cls.rule_id] = cls
    return cls


def get_all_rules() -> dict[str, type[BaseRule]]:
    """Return all registered rule classes."""
    return dict(_rule_registry)


def get_rules_by_category(category: str) -> dict[str, type[BaseRule]]:
    """Return registered rules filtered by category."""
    return {k: v for k, v in _rule_registry.items() if v.category == category}
