"""Test coverage and quality rules."""

from __future__ import annotations

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


@register_rule
class PrimaryKeyTestRequiredRule(BaseRule):
    rule_id = "testing.primary_key_test_required"
    category = "testing"
    description = "Every model must have a unique + not_null test on its primary key"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue

            test_names = {t.name.lower() for t in model.tests}
            test_types = {(t.test_type or "").lower() for t in model.tests}

            has_unique = any("unique" in n or "unique" in test_types for n in test_names)
            has_not_null = any("not_null" in n for n in test_names)

            if not (has_unique and has_not_null):
                missing = []
                if not has_unique:
                    missing.append("unique")
                if not has_not_null:
                    missing.append("not_null")
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' is missing primary key test(s): {', '.join(missing)}",
                    suggestion="Add unique and not_null tests on the primary key column in your schema YAML",
                ))
        return violations


@register_rule
class MinimumTestCoverageRule(BaseRule):
    rule_id = "testing.minimum_test_coverage"
    category = "testing"
    description = "Every model must have at least N tests"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        min_tests = self.get_rule_config_value(context.governance_config, "min_tests_per_model", 2)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if len(model.tests) < min_tests:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' has {len(model.tests)} test(s) (minimum required: {min_tests})",
                    suggestion=f"Add at least {min_tests - len(model.tests)} more test(s) in your schema YAML",
                ))
        return violations


@register_rule
class StagingFreshnessRequiredRule(BaseRule):
    rule_id = "testing.staging_freshness_required"
    category = "testing"
    description = "All sources feeding staging models must have freshness checks"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        source_ids_used_by_staging: set[str] = set()
        for model in context.manifest_data.models.values():
            if model.layer == "staging":
                source_ids_used_by_staging.update(model.depends_on_sources)

        for src_id in source_ids_used_by_staging:
            source = context.manifest_data.sources.get(src_id)
            if not source:
                continue
            has_freshness = source.loaded_at_field is not None or (
                source.freshness is not None and source.freshness.max_loaded_at is not None
            )
            if not has_freshness:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=f"{source.source_name}.{source.name}",
                    file_path="",
                    message=f"Source '{source.source_name}.{source.name}' feeds staging models but has no freshness check",
                    suggestion="Add loaded_at_field and freshness config to the source definition",
                ))
        return violations


@register_rule
class MartsHaveContractRule(BaseRule):
    rule_id = "testing.marts_have_contract"
    category = "testing"
    description = "Mart models should define a model contract for column type enforcement"
    default_severity = Severity.INFO

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if model.layer != "marts":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if not model.contract_enforced:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Mart model '{model.name}' does not have a model contract enforced",
                    suggestion="Add contract: {enforced: true} to the model config for column type enforcement",
                ))
        return violations


@register_rule
class NoDisabledTestsRule(BaseRule):
    rule_id = "testing.no_disabled_tests"
    category = "testing"
    description = "Tests should not be disabled"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            enabled_key = model.config.get("enabled")
            if enabled_key is False:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' has disabled config — its tests may be skipped",
                    suggestion="Remove 'enabled: false' or fix the underlying issue instead of disabling",
                ))
        return violations


@register_rule
class ColumnTestCoverageRule(BaseRule):
    rule_id = "testing.column_test_coverage"
    category = "testing"
    description = "At least a minimum percentage of documented columns should have tests"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        min_pct = float(self.get_rule_config_value(context.governance_config, "min_coverage_pct", 0.5))
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if not model.columns:
                continue  # No schema.yml columns documented — skip (schema_yml_exists covers that)

            columns_with_tests = {t.column_name for t in model.tests if t.column_name}
            documented_cols = set(model.columns.keys())
            if not documented_cols:
                continue

            coverage = len(columns_with_tests & documented_cols) / len(documented_cols)
            if coverage < min_pct:
                pct_actual = int(coverage * 100)
                pct_required = int(min_pct * 100)
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=(
                        f"Model '{model.name}' has {pct_actual}% column test coverage "
                        f"(minimum required: {pct_required}%). "
                        f"{len(columns_with_tests & documented_cols)} of {len(documented_cols)} "
                        f"documented columns have tests."
                    ),
                    suggestion=(
                        f"Add tests (not_null, accepted_values, relationships) for at least "
                        f"{pct_required}% of the model's documented columns in schema YAML."
                    ),
                ))
        return violations
