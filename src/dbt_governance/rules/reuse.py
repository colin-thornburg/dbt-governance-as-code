"""Re-use and redundancy detection rules.

These rules surface opportunities to consolidate duplicated logic across models —
a critical problem in legacy ETL migrations where each pipeline was independent
and dbt's shared-model capabilities were never leveraged.

The goal is not to flag every similarity, but to find the high-confidence cases
where two or more models are clearly doing the same work and should share a
common upstream model instead.
"""

from __future__ import annotations

import re
from collections import defaultdict

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


@register_rule
class DuplicateSourceStagingRule(BaseRule):
    rule_id = "reuse.duplicate_source_staging"
    category = "reuse"
    description = (
        "Multiple staging models reference the same source table — "
        "each should have exactly one staging model; downstream models should ref() that one"
    )
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        # Map source_id -> list of staging models that depend on it
        source_to_staging: dict[str, list[str]] = defaultdict(list)

        for model in context.manifest_data.models.values():
            if model.layer != "staging":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            for src_id in model.depends_on_sources:
                source_to_staging[src_id].append(model.unique_id)

        for src_id, staging_ids in source_to_staging.items():
            if len(staging_ids) < 2:
                continue

            src = context.manifest_data.sources.get(src_id)
            src_label = f"{src.source_name}.{src.name}" if src else src_id

            staging_names = []
            for mid in staging_ids:
                m = context.manifest_data.models.get(mid)
                staging_names.append(m.name if m else mid)

            for mid in staging_ids:
                model = context.manifest_data.models.get(mid)
                if not model:
                    continue
                others = [n for n in staging_names if n != model.name]
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=(
                        f"Source '{src_label}' is staged by multiple models: "
                        f"{', '.join(staging_names)}. "
                        "Each source table should have exactly one staging model."
                    ),
                    suggestion=(
                        f"Consolidate into a single staging model (e.g., keep '{staging_names[0]}'). "
                        f"Models {', '.join(others)} should ref() that staging model instead of "
                        "staging the same source independently. "
                        "This prevents divergent transformations on the same raw data."
                    ),
                ))
        return violations


@register_rule
class SharedCTECandidatesRule(BaseRule):
    rule_id = "reuse.shared_cte_candidates"
    category = "reuse"
    description = (
        "The same CTE name appears across many models, suggesting duplicated logic "
        "that should be extracted into a shared intermediate model"
    )
    default_severity = Severity.INFO

    # Minimum number of models that must share a CTE name to flag it
    _DEFAULT_MIN_OCCURRENCES = 3

    # CTE names that are too generic to be meaningful (import boilerplate)
    _SKIP_NAMES = frozenset({
        "final", "base", "source", "raw", "renamed", "casted", "filtered",
        "joined", "aggregated", "windowed", "pivoted", "unpivoted",
        "orders", "customers", "payments",  # skip trivially common domain names
    })

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        min_occurrences = self.get_rule_config_value(
            context.governance_config, "min_occurrences", self._DEFAULT_MIN_OCCURRENCES
        )
        violations = []

        cte_name_pattern = re.compile(r"(\w+)\s+as\s*\(", re.IGNORECASE)

        # Map cte_name -> list of (model_name, file_path)
        cte_occurrences: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code or context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            found_in_model: set[str] = set()
            for match in cte_name_pattern.finditer(sql):
                name = match.group(1).lower()
                if name in self._SKIP_NAMES:
                    continue
                if name not in found_in_model:
                    cte_occurrences[name].append((model.name, model.file_path))
                    found_in_model.add(name)

        # Only flag CTEs that appear in enough models to suggest real duplication
        already_flagged_models: set[str] = set()
        for cte_name, occurrences in cte_occurrences.items():
            if len(occurrences) < min_occurrences:
                continue

            model_names = [o[0] for o in occurrences]

            for model_name, file_path in occurrences:
                if model_name in already_flagged_models:
                    continue
                already_flagged_models.add(model_name)

                others = [n for n in model_names if n != model_name]
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model_name,
                    file_path=file_path,
                    message=(
                        f"CTE named '{cte_name}' appears in {len(occurrences)} models: "
                        f"{', '.join(model_names[:5])}{'...' if len(model_names) > 5 else ''}. "
                        "This suggests duplicated logic that should be a shared model."
                    ),
                    suggestion=(
                        f"Extract the '{cte_name}' logic into a dedicated intermediate model "
                        f"(e.g., int_{cte_name}_base.sql) and have the {len(occurrences)} models "
                        "ref() it instead. This ensures consistent logic and a single place to update."
                    ),
                ))
        return violations


@register_rule
class MultipleModelsFromSameSourceRule(BaseRule):
    rule_id = "reuse.multiple_models_from_same_source"
    category = "reuse"
    description = (
        "Multiple non-staging models reference the same source table directly — "
        "they should all go through a single shared staging model"
    )
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        # Map source_id -> list of non-staging models that depend on it directly
        source_to_models: dict[str, list[str]] = defaultdict(list)

        for model in context.manifest_data.models.values():
            if model.layer == "staging":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            for src_id in model.depends_on_sources:
                source_to_models[src_id].append(model.unique_id)

        for src_id, model_ids in source_to_models.items():
            if len(model_ids) < 2:
                continue

            src = context.manifest_data.sources.get(src_id)
            src_label = f"{src.source_name}.{src.name}" if src else src_id

            model_names = []
            for mid in model_ids:
                m = context.manifest_data.models.get(mid)
                model_names.append(m.name if m else mid)

            for mid in model_ids:
                model = context.manifest_data.models.get(mid)
                if not model:
                    continue
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=(
                        f"Source '{src_label}' is referenced directly by {len(model_ids)} "
                        f"non-staging models: {', '.join(model_names)}. "
                        "Each source should be staged once and shared via ref()."
                    ),
                    suggestion=(
                        f"Create a single staging model for source '{src_label}' "
                        "(e.g., stg_<source>__<table>.sql) and update all "
                        f"{len(model_ids)} models to ref() it. "
                        "This centralizes source field mapping and ensures type casting "
                        "is done consistently in one place."
                    ),
                ))
        return violations


@register_rule
class IdenticalSelectColumnsRule(BaseRule):
    rule_id = "reuse.identical_select_columns"
    category = "reuse"
    description = (
        "Multiple models select the exact same set of columns from the same base — "
        "strong signal of copy-paste duplication that should be a shared model"
    )
    default_severity = Severity.INFO

    _MIN_COLUMNS = 5  # Only flag when there are enough columns to be meaningful

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        col_select_pattern = re.compile(
            r"select\s+([\w\s,.*]+?)\s+from\s+\{\{\s*(?:ref|source)\s*\(['\"](\w+)['\"]",
            re.IGNORECASE | re.DOTALL,
        )

        # Map (frozenset_of_columns, source_model) -> list of (model_name, file_path)
        column_groups: dict[tuple, list[tuple[str, str]]] = defaultdict(list)

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code or context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            match = col_select_pattern.search(sql)
            if not match:
                continue

            col_text = match.group(1)
            source_ref = match.group(2).lower()

            # Parse column names — skip wildcards
            if "*" in col_text:
                continue
            cols = frozenset(
                c.strip().lower().split(".")[-1].split(" as ")[-1].strip()
                for c in col_text.split(",")
                if c.strip()
            )
            if len(cols) < self._MIN_COLUMNS:
                continue

            key = (cols, source_ref)
            column_groups[key].append((model.name, model.file_path))

        for (cols, source_ref), models in column_groups.items():
            if len(models) < 2:
                continue

            model_names = [m[0] for m in models]
            for model_name, file_path in models:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model_name,
                    file_path=file_path,
                    message=(
                        f"Model '{model_name}' selects the same {len(cols)} columns from "
                        f"'{source_ref}' as: {', '.join(n for n in model_names if n != model_name)}. "
                        "This is likely duplicated logic."
                    ),
                    suggestion=(
                        f"Extract the shared column selection from '{source_ref}' into a "
                        "single intermediate model and ref() it from all consumers. "
                        "This ensures column aliasing and type casting are done once."
                    ),
                ))
        return violations
