"""DAG structure and layering rules."""

from __future__ import annotations

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


@register_rule
class StagingRefsSourceOnlyRule(BaseRule):
    rule_id = "structure.staging_refs_source_only"
    category = "structure"
    description = "Staging models may only reference sources, not other models"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if model.layer != "staging":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if model.depends_on_models:
                ref_names = []
                for dep_id in model.depends_on_models:
                    dep_model = context.manifest_data.models.get(dep_id)
                    ref_names.append(dep_model.name if dep_model else dep_id)
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Staging model '{model.name}' references model(s): {', '.join(ref_names)}",
                    suggestion="Staging models should only reference sources via source(). Move model refs to intermediate layer.",
                ))
        return violations


@register_rule
class MartsNoSourceRefsRule(BaseRule):
    rule_id = "structure.marts_no_source_refs"
    category = "structure"
    description = "Mart models must not directly reference sources"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if model.layer != "marts":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if model.depends_on_sources:
                src_names = []
                for src_id in model.depends_on_sources:
                    src = context.manifest_data.sources.get(src_id)
                    src_names.append(f"{src.source_name}.{src.name}" if src else src_id)
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Mart model '{model.name}' directly references source(s): {', '.join(src_names)}",
                    suggestion="Mart models should reference staging or intermediate models, not sources directly.",
                ))
        return violations


@register_rule
class NoCrossLayerSkippingRule(BaseRule):
    rule_id = "structure.no_cross_layer_skipping"
    category = "structure"
    description = "Models should not skip layers"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if model.layer != "marts":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            for dep_id in model.depends_on_models:
                dep = context.manifest_data.models.get(dep_id)
                if dep and dep.layer == "staging":
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model.name,
                        file_path=model.file_path,
                        message=f"Mart model '{model.name}' directly references staging model '{dep.name}' — skipping intermediate layer",
                        suggestion="Add an intermediate model between staging and marts for transformation logic.",
                    ))
        return violations


@register_rule
class MaxDagDepthRule(BaseRule):
    rule_id = "structure.max_dag_depth"
    category = "structure"
    description = "No model should have more than N upstream ancestors"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        max_depth = self.get_rule_config_value(context.governance_config, "max_depth", 8)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            depth = context.manifest_data.dag.depth(model.unique_id)
            if depth > max_depth:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' has DAG depth of {depth} (max allowed: {max_depth})",
                    suggestion="Consider flattening the dependency chain or consolidating intermediate models.",
                ))
        return violations


@register_rule
class MaxFanoutRule(BaseRule):
    rule_id = "structure.max_fanout"
    category = "structure"
    description = "No model should be referenced by more than N downstream models"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        max_children = self.get_rule_config_value(context.governance_config, "max_children", 10)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            fanout = context.manifest_data.dag.fanout(model.unique_id)
            if fanout > max_children:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' has {fanout} direct downstream dependents (max allowed: {max_children})",
                    suggestion="Consider whether some dependents could share an intermediate model.",
                ))
        return violations


@register_rule
class NoOrphanModelsRule(BaseRule):
    rule_id = "structure.no_orphan_models"
    category = "structure"
    description = "Every model should have at least one downstream dependency or be an exposure endpoint"
    default_severity = Severity.INFO

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        exposure_deps: set[str] = set()
        for exp in context.manifest_data.exposures.values():
            exposure_deps.update(exp.depends_on)

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            has_children = bool(context.manifest_data.dag.children.get(model.unique_id))
            is_exposure_endpoint = model.unique_id in exposure_deps
            if not has_children and not is_exposure_endpoint:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' has no downstream dependents and is not an exposure endpoint",
                    suggestion="Either add a downstream consumer, create an exposure, or remove the model if unused.",
                ))
        return violations


@register_rule
class NoRejoinPatternsRule(BaseRule):
    rule_id = "structure.no_rejoin_patterns"
    category = "structure"
    description = "Detect diamond dependency patterns"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        diamonds = context.manifest_data.dag.find_diamonds()
        for node_id, parent1, parent2 in diamonds:
            model = context.manifest_data.models.get(node_id)
            if not model:
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            p1 = context.manifest_data.models.get(parent1)
            p2 = context.manifest_data.models.get(parent2)
            p1_name = p1.name if p1 else parent1
            p2_name = p2.name if p2 else parent2
            violations.append(Violation(
                rule_id=self.rule_id,
                severity=severity,
                model_name=model.name,
                file_path=model.file_path,
                message=f"Diamond dependency: '{model.name}' depends on '{p1_name}' and '{p2_name}' which share common ancestors",
                suggestion="Consider consolidating shared logic into a single upstream model.",
            ))
        return violations


@register_rule
class ModelDirectoriesMatchLayersRule(BaseRule):
    rule_id = "structure.model_directories_match_layers"
    category = "structure"
    description = "Models must live in the directory matching their layer"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        layer_dir_map = {
            "staging": "staging",
            "intermediate": "intermediate",
            "marts": "marts",
        }

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            if not model.file_path:
                continue

            name = model.name.lower()
            if name.startswith("stg_"):
                expected_dir = layer_dir_map["staging"]
            elif name.startswith("int_"):
                expected_dir = layer_dir_map["intermediate"]
            elif name.startswith(("fct_", "dim_")):
                expected_dir = layer_dir_map["marts"]
            else:
                continue

            if f"/{expected_dir}/" not in model.file_path.lower() and not model.file_path.lower().startswith(f"{expected_dir}/"):
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' has a '{expected_dir}' naming prefix but is not in the models/{expected_dir}/ directory",
                    suggestion=f"Move to models/{expected_dir}/",
                ))
        return violations
