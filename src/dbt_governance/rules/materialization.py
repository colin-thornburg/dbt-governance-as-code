"""Materialization pattern rules."""

from __future__ import annotations

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


@register_rule
class StagingMustBeViewRule(BaseRule):
    rule_id = "materialization.staging_must_be_view"
    category = "materialization"
    description = "Staging models should be materialized as views"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if model.layer != "staging":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if model.materialization and model.materialization.lower() not in ("view", "ephemeral"):
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Staging model '{model.name}' is materialized as '{model.materialization}' instead of 'view'",
                    suggestion="Change materialization to 'view' (or 'ephemeral') in dbt_project.yml or model config",
                ))
        return violations


@register_rule
class IncrementalMustHaveUniqueKeyRule(BaseRule):
    rule_id = "materialization.incremental_must_have_unique_key"
    category = "materialization"
    description = "Incremental models must specify a unique_key"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if model.materialization and model.materialization.lower() == "incremental":
                unique_key = model.config.get("unique_key")
                if not unique_key:
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model.name,
                        file_path=model.file_path,
                        message=f"Incremental model '{model.name}' does not specify a unique_key",
                        suggestion="Add unique_key to the model config: {{ config(unique_key='your_key_column') }}",
                    ))
        return violations


@register_rule
class IncrementalMustHaveOnSchemaChangeRule(BaseRule):
    rule_id = "materialization.incremental_must_have_on_schema_change"
    category = "materialization"
    description = "Incremental models should define on_schema_change strategy"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if model.materialization and model.materialization.lower() == "incremental":
                on_schema_change = model.config.get("on_schema_change")
                if not on_schema_change:
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model.name,
                        file_path=model.file_path,
                        message=f"Incremental model '{model.name}' does not define on_schema_change strategy",
                        suggestion="Add on_schema_change='append_new_columns' (or 'sync_all_columns', 'fail') to the model config",
                    ))
        return violations
