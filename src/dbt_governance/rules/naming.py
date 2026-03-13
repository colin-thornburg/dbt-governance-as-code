"""Naming convention rules."""

from __future__ import annotations

import re

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


@register_rule
class StagingPrefixRule(BaseRule):
    rule_id = "naming.staging_prefix"
    category = "naming"
    description = "Staging models must follow stg_<source>__<entity> naming"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []
        pattern = re.compile(r"^stg_[a-z0-9_]+__[a-z0-9_]+$")

        for model in context.manifest_data.models.values():
            if model.layer != "staging":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if not pattern.match(model.name):
                source_hint = ""
                if model.depends_on_sources:
                    src_name = model.depends_on_sources[0].split(".")[-1] if model.depends_on_sources else "source"
                    source_hint = f"stg_{src_name}__{model.name.removeprefix('stg_').split('__')[-1]}"
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Staging model '{model.name}' does not follow stg_<source>__<entity> naming",
                    suggestion=f"Rename to: {source_hint}" if source_hint else "Rename to match stg_<source>__<entity> pattern",
                ))
        return violations


@register_rule
class IntermediatePrefixRule(BaseRule):
    rule_id = "naming.intermediate_prefix"
    category = "naming"
    description = "Intermediate models must follow int_<entity>_<verb> naming"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if model.layer != "intermediate":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if not model.name.startswith("int_"):
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Intermediate model '{model.name}' does not start with 'int_' prefix",
                    suggestion=f"Rename to: int_{model.name}",
                ))
        return violations


@register_rule
class MartsPrefixRule(BaseRule):
    rule_id = "naming.marts_prefix"
    category = "naming"
    description = "Mart models should use fct_ or dim_ prefixes"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if model.layer != "marts":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if not model.name.startswith(("fct_", "dim_")):
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Mart model '{model.name}' does not use fct_ or dim_ prefix",
                    suggestion=f"Rename to fct_{model.name} (fact) or dim_{model.name} (dimension)",
                ))
        return violations


@register_rule
class SourceSchemaRequiredRule(BaseRule):
    rule_id = "naming.source_schema_required"
    category = "naming"
    description = "All sources must have an explicit schema defined"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for source in context.manifest_data.sources.values():
            if not source.schema_name:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=f"{source.source_name}.{source.name}",
                    file_path="",
                    message=f"Source '{source.source_name}.{source.name}' has no explicit schema defined",
                    suggestion="Add a 'schema' property to the source definition in your YAML file",
                ))
        return violations


@register_rule
class ModelFileMatchesNameRule(BaseRule):
    rule_id = "naming.model_file_matches_name"
    category = "naming"
    description = "SQL filename must match the model name"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if not model.file_path:
                continue
            filename = model.file_path.rsplit("/", 1)[-1].removesuffix(".sql")
            if filename != model.name:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Filename '{filename}.sql' does not match model name '{model.name}'",
                    suggestion=f"Rename file to {model.name}.sql",
                ))
        return violations
