"""Meta-governance rules — config hygiene, ownership, access controls."""

from __future__ import annotations

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


@register_rule
class ModelOwnershipRequiredRule(BaseRule):
    rule_id = "governance.model_ownership_required"
    category = "governance"
    description = "All models must have a meta.owner or group defined"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            has_owner = model.meta.get("owner") or model.group
            if not has_owner:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' has no owner (meta.owner or group) defined",
                    suggestion="Add meta: {{owner: 'team-name'}} or group: 'team-name' to the model config",
                ))
        return violations


@register_rule
class PublicModelsNeedContractRule(BaseRule):
    rule_id = "governance.public_models_need_contract"
    category = "governance"
    description = "Models with public access must have a contract enforced"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if model.access == "public" and not model.contract_enforced:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Public model '{model.name}' does not have a contract enforced",
                    suggestion="Add contract: {{enforced: true}} — public models should guarantee column types for consumers",
                ))
        return violations
