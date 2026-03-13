"""Documentation completeness rules."""

from __future__ import annotations

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


@register_rule
class ModelDescriptionRequiredRule(BaseRule):
    rule_id = "documentation.model_description_required"
    category = "documentation"
    description = "Models in specified layers must have a description"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        layers = self.get_rule_config_value(context.governance_config, "layers", ["marts", "intermediate"])
        violations = []

        for model in context.manifest_data.models.values():
            if model.layer not in layers:
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if not model.description or not model.description.strip():
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' ({model.layer} layer) has no description",
                    suggestion="Add a description in the schema YAML file for this model",
                ))
        return violations


@register_rule
class ColumnDescriptionRequiredRule(BaseRule):
    rule_id = "documentation.column_description_required"
    category = "documentation"
    description = "All columns in mart models must have descriptions"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        layers = self.get_rule_config_value(context.governance_config, "layers", ["marts"])
        violations = []

        for model in context.manifest_data.models.values():
            if model.layer not in layers:
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if not model.columns:
                continue

            undocumented = [
                col_name for col_name, col in model.columns.items()
                if not col.description or not col.description.strip()
            ]
            if undocumented:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' has {len(undocumented)} undocumented column(s): {', '.join(undocumented[:5])}{'...' if len(undocumented) > 5 else ''}",
                    suggestion="Add descriptions for all columns in the schema YAML file",
                ))
        return violations


@register_rule
class SourceDescriptionRequiredRule(BaseRule):
    rule_id = "documentation.source_description_required"
    category = "documentation"
    description = "All sources must have a description"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for source in context.manifest_data.sources.values():
            if not source.description or not source.description.strip():
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=f"{source.source_name}.{source.name}",
                    file_path="",
                    message=f"Source '{source.source_name}.{source.name}' has no description",
                    suggestion="Add a description to the source definition in your YAML file",
                ))
        return violations


@register_rule
class SchemaYmlExistsRule(BaseRule):
    rule_id = "documentation.schema_yml_exists"
    category = "documentation"
    description = "Every model directory must contain a corresponding schema YAML file"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        model_dirs: set[str] = set()
        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if "/" in model.file_path:
                dir_path = model.file_path.rsplit("/", 1)[0]
                model_dirs.add(dir_path)

        schema_dirs: set[str] = set()
        for schema_path in context.schema_files:
            if "/" in schema_path:
                schema_dirs.add(schema_path.rsplit("/", 1)[0])

        for model_dir in model_dirs:
            if model_dir not in schema_dirs:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model_dir,
                    file_path=model_dir,
                    message=f"Directory '{model_dir}' contains models but no schema YAML file",
                    suggestion=f"Create a schema YAML file (e.g., _{model_dir.rsplit('/', 1)[-1]}__models.yml) in this directory",
                ))
        return violations
