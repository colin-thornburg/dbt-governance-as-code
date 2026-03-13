"""SQL style rules — supplements sqlfluff with dbt-specific patterns."""

from __future__ import annotations

import re

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


@register_rule
class CTEPatternRule(BaseRule):
    rule_id = "style.cte_pattern"
    category = "style"
    description = "Models should use import CTEs (refs at top) followed by logical CTEs"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        ref_pattern = re.compile(r"\{\{\s*(ref|source)\s*\(")

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code
            if not sql:
                sql = context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            cte_pattern = re.compile(r"(\w+)\s+as\s*\(", re.IGNORECASE)
            ctes = list(cte_pattern.finditer(sql))
            if len(ctes) < 2:
                continue

            found_non_import = False
            has_violation = False
            for match in ctes:
                cte_start = match.start()
                next_cte = sql.find("\n)", cte_start)
                if next_cte == -1:
                    next_cte = len(sql)
                cte_body = sql[cte_start:next_cte]

                is_import = bool(ref_pattern.search(cte_body))
                if not is_import:
                    found_non_import = True
                elif found_non_import:
                    has_violation = True
                    break

            if has_violation:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=f"Model '{model.name}' has ref()/source() calls after logical CTEs — imports should come first",
                    suggestion="Move all import CTEs (those containing ref/source) to the top of the WITH block",
                ))
        return violations


@register_rule
class NoHardcodedSchemaRule(BaseRule):
    rule_id = "style.no_hardcoded_schema"
    category = "style"
    description = "SQL must not contain hardcoded schema or database references"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        hardcoded = re.compile(
            r"""(?:from|join)\s+(?!.*\{\{)['"`]?\w+['"`]?\.['"`]?\w+['"`]?\.['"`]?\w+['"`]?""",
            re.IGNORECASE,
        )

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code
            if not sql:
                sql = context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            for i, line in enumerate(sql.splitlines(), 1):
                if "{{" in line or "{%" in line:
                    continue
                if hardcoded.search(line):
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model.name,
                        file_path=model.file_path,
                        line_number=i,
                        message=f"Model '{model.name}' contains a hardcoded database.schema.table reference on line {i}",
                        suggestion="Use {{ ref('model_name') }} or {{ source('source', 'table') }} instead",
                    ))
                    break
        return violations


@register_rule
class NoSelectStarInMartsRule(BaseRule):
    rule_id = "style.no_select_star_in_marts"
    category = "style"
    description = "Mart models should not use SELECT * — explicitly list columns"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        select_star = re.compile(r"select\s+\*", re.IGNORECASE)

        for model in context.manifest_data.models.values():
            if model.layer != "marts":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code
            if not sql:
                sql = context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            final_lines = sql.strip().splitlines()
            last_select_idx = None
            for i in range(len(final_lines) - 1, -1, -1):
                if "select" in final_lines[i].lower():
                    last_select_idx = i
                    break

            if last_select_idx is not None:
                final_section = "\n".join(final_lines[last_select_idx:])
                if select_star.search(final_section):
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model.name,
                        file_path=model.file_path,
                        message=f"Mart model '{model.name}' uses SELECT * — columns should be explicitly listed",
                        suggestion="Replace SELECT * with an explicit column list for better documentation and contract compliance",
                    ))
        return violations


@register_rule
class FinalSelectFromNamedCTERule(BaseRule):
    rule_id = "style.final_select_from_named_cte"
    category = "style"
    description = "The final SELECT should reference a named CTE"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        ref_source = re.compile(r"\{\{\s*(ref|source)\s*\(")

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code
            if not sql:
                sql = context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            if "with" not in sql.lower():
                continue

            lines = sql.strip().splitlines()
            for i in range(len(lines) - 1, -1, -1):
                line = lines[i].strip().lower()
                if line.startswith("from") or line.startswith("join"):
                    if ref_source.search(lines[i]):
                        violations.append(Violation(
                            rule_id=self.rule_id,
                            severity=severity,
                            model_name=model.name,
                            file_path=model.file_path,
                            message=f"Model '{model.name}' has a final SELECT that references a ref/source directly instead of a named CTE",
                            suggestion="Create an import CTE for the ref/source at the top and reference the CTE name in the final SELECT",
                        ))
                    break
        return violations


@register_rule
class RefsInCTEsNotInlineRule(BaseRule):
    rule_id = "style.refs_in_ctes_not_inline"
    category = "style"
    description = "ref() calls should be in import CTEs, not inline in joins"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        join_ref = re.compile(r"join\s+\{\{\s*ref\s*\(", re.IGNORECASE)

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code
            if not sql:
                sql = context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            for i, line in enumerate(sql.splitlines(), 1):
                if join_ref.search(line):
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model.name,
                        file_path=model.file_path,
                        line_number=i,
                        message=f"Model '{model.name}' has an inline ref() in a JOIN on line {i}",
                        suggestion="Move the ref() into an import CTE at the top of the file and join against the CTE name",
                    ))
                    break
        return violations
