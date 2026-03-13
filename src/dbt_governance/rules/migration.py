"""Legacy migration anti-pattern rules.

These rules specifically target SQL patterns that indicate a model was migrated
from a legacy ETL tool (Talend, Informatica, SSIS, Pentaho, etc.) without being
restructured as proper dbt patterns. They form the basis of the "Legacy Migration
Report" — a prioritized remediation list for platform teams.
"""

from __future__ import annotations

import re

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


@register_rule
class NoRefOrSourceUsageRule(BaseRule):
    rule_id = "migration.no_ref_or_source"
    category = "migration"
    description = (
        "Model contains no ref() or source() calls — likely a direct SQL migration "
        "from a legacy ETL tool (Talend, Informatica, etc.) that bypasses dbt lineage"
    )
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        ref_or_source = re.compile(r"\{\{\s*(ref|source)\s*\(", re.IGNORECASE)

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code or context.sql_files.get(model.file_path, "")
            if not sql:
                continue
            # Skip models that are clearly just config/empty
            if len(sql.strip()) < 20:
                continue
            if not ref_or_source.search(sql):
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=(
                        f"Model '{model.name}' has no ref() or source() calls — "
                        "it likely references tables directly, which breaks dbt lineage "
                        "and suggests a raw ETL migration"
                    ),
                    suggestion=(
                        "Replace direct table references with {{ source('source_name', 'table_name') }} "
                        "for raw tables, or {{ ref('model_name') }} for dbt models. "
                        "Define any raw tables as sources in a sources.yml file."
                    ),
                ))
        return violations


@register_rule
class DDLStatementsRule(BaseRule):
    rule_id = "migration.ddl_statements"
    category = "migration"
    description = (
        "Model contains DDL/DML statements (CREATE TABLE, INSERT INTO, TRUNCATE, etc.) "
        "that are ETL tool patterns incompatible with dbt's materialization model"
    )
    default_severity = Severity.ERROR

    # Patterns that indicate procedural ETL SQL, not a dbt SELECT model
    _DDL_PATTERN = re.compile(
        r"""^\s*(
            create\s+(or\s+replace\s+)?(table|view|temporary\s+table)|
            insert\s+(into|overwrite)|
            truncate\s+(table\s+)?|
            drop\s+(table|view)|
            alter\s+table|
            merge\s+into|
            update\s+\w+\s+set|
            delete\s+from
        )""",
        re.IGNORECASE | re.VERBOSE | re.MULTILINE,
    )

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code or context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            for i, line in enumerate(sql.splitlines(), 1):
                # Skip Jinja comments and blocks
                if "{#" in line or "{%" in line:
                    continue
                if self._DDL_PATTERN.match(line):
                    statement = line.strip().split()[0].upper()
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model.name,
                        file_path=model.file_path,
                        line_number=i,
                        message=(
                            f"Model '{model.name}' contains a '{statement}' statement on line {i} — "
                            "this is an ETL pattern that dbt handles via materializations, not explicit DDL"
                        ),
                        suggestion=(
                            "Remove DDL/DML statements. Use dbt materializations instead: "
                            "set 'materialized: table' or 'materialized: incremental' in config. "
                            "For INSERT patterns, rewrite as a SELECT that dbt will materialize. "
                            "For MERGE/UPDATE patterns, use an incremental model with unique_key."
                        ),
                    ))
                    break  # One violation per model is enough
        return violations


@register_rule
class HardcodedEnvironmentSchemaRule(BaseRule):
    rule_id = "migration.hardcoded_environment_schema"
    category = "migration"
    description = (
        "Model references environment-specific schema names (prod, dev, staging, uat, raw, etc.) "
        "hardcoded in SQL — a common legacy migration pattern that breaks across environments"
    )
    default_severity = Severity.ERROR

    # Common environment/layer schema names that should never be hardcoded
    _ENV_SCHEMA_PATTERN = re.compile(
        r"""(?:from|join)\s+['"`]?(?:
            prod|production|
            dev|development|
            staging|stage|stg|
            uat|qa|test|
            raw|source|src|
            edw|dw|dwh|
            sandbox|
            analytics
        )['"`]?\.""",
        re.IGNORECASE | re.VERBOSE,
    )

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code or context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            for i, line in enumerate(sql.splitlines(), 1):
                if "{{" in line or "{%" in line:
                    continue
                if self._ENV_SCHEMA_PATTERN.search(line):
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model.name,
                        file_path=model.file_path,
                        line_number=i,
                        message=(
                            f"Model '{model.name}' references an environment-specific schema name "
                            f"on line {i} — this is a legacy migration pattern that will break "
                            "in non-production environments"
                        ),
                        suggestion=(
                            "Replace hardcoded schema references with dbt sources or refs. "
                            "For raw source tables: define a sources.yml entry and use "
                            "{{ source('source_name', 'table') }}. "
                            "For other dbt models: use {{ ref('model_name') }}."
                        ),
                    ))
                    break
        return violations


@register_rule
class MissingSourceDefinitionRule(BaseRule):
    rule_id = "migration.missing_source_definition"
    category = "migration"
    description = (
        "Model uses source() calls but the referenced source is not defined in any sources.yml — "
        "indicates an incomplete migration where source definitions were not created"
    )
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        source_call = re.compile(r"""\{\{\s*source\s*\(\s*['"](\w+)['"]\s*,\s*['"](\w+)['"]\s*\)""")

        # Build set of defined source keys
        defined_sources: set[tuple[str, str]] = set()
        for src in context.manifest_data.sources.values():
            defined_sources.add((src.source_name.lower(), src.name.lower()))

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code or context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            for match in source_call.finditer(sql):
                source_name = match.group(1).lower()
                table_name = match.group(2).lower()
                if (source_name, table_name) not in defined_sources:
                    line_number = sql[: match.start()].count("\n") + 1
                    violations.append(Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model.name,
                        file_path=model.file_path,
                        line_number=line_number,
                        message=(
                            f"Model '{model.name}' calls source('{source_name}', '{table_name}') "
                            "but this source is not defined in any sources.yml"
                        ),
                        suggestion=(
                            f"Add a sources.yml entry for source '{source_name}' with table '{table_name}'. "
                            "Example:\n"
                            "  sources:\n"
                            f"    - name: {source_name}\n"
                            "      tables:\n"
                            f"        - name: {table_name}"
                        ),
                    ))
        return violations


@register_rule
class NoLayeringRule(BaseRule):
    rule_id = "migration.no_layering"
    category = "migration"
    description = (
        "Model is not in any recognized dbt layer (staging/intermediate/marts) — "
        "likely a monolithic SQL migration that wasn't restructured into the dbt layering pattern"
    )
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        # Layer indicators: naming convention prefix OR directory path
        layer_name_patterns = re.compile(r"^(stg_|int_|fct_|dim_)", re.IGNORECASE)
        layer_path_patterns = re.compile(
            r"/(staging|intermediate|marts|mart)/", re.IGNORECASE
        )

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            # If it has neither a layer prefix nor lives in a layer directory, flag it
            has_name_layer = bool(layer_name_patterns.match(model.name))
            has_path_layer = bool(layer_path_patterns.search(model.file_path or ""))

            if not has_name_layer and not has_path_layer:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=(
                        f"Model '{model.name}' has no dbt layer structure — "
                        "it doesn't follow naming conventions (stg_, int_, fct_, dim_) "
                        "and isn't in a layer directory (staging/, intermediate/, marts/)"
                    ),
                    suggestion=(
                        "Restructure this model into the dbt layering pattern:\n"
                        "  1. If it reads from a raw source: rename to stg_<source>__<entity>.sql "
                        "     and move to models/staging/\n"
                        "  2. If it applies business transformations: rename to int_<entity>_<verb>.sql "
                        "     and move to models/intermediate/\n"
                        "  3. If it's a final output: rename to fct_<entity>.sql or dim_<entity>.sql "
                        "     and move to models/marts/"
                    ),
                ))
        return violations
