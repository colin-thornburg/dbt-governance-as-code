"""Pydantic models for .dbt-governance.yml configuration."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AIProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"


class RuleConfig(BaseModel):
    enabled: bool = True
    severity: Severity = Severity.WARNING
    description: str = ""

    model_config = {"extra": "allow"}


class NamingRules(BaseModel):
    enabled: bool = True
    rules: dict[str, RuleConfig] = Field(default_factory=dict)


class StructureRules(BaseModel):
    enabled: bool = True
    rules: dict[str, RuleConfig] = Field(default_factory=dict)


class TestingRules(BaseModel):
    enabled: bool = True
    rules: dict[str, RuleConfig] = Field(default_factory=dict)


class DocumentationRules(BaseModel):
    enabled: bool = True
    rules: dict[str, RuleConfig] = Field(default_factory=dict)


class MaterializationRules(BaseModel):
    enabled: bool = True
    rules: dict[str, RuleConfig] = Field(default_factory=dict)


class StyleRules(BaseModel):
    enabled: bool = True
    rules: dict[str, RuleConfig] = Field(default_factory=dict)


class MigrationRules(BaseModel):
    """Rules that detect legacy ETL tool anti-patterns (Talend, Informatica, SSIS, etc.)
    migrated to dbt without proper restructuring. These form the basis of the
    Legacy Migration Report."""
    enabled: bool = True
    rules: dict[str, RuleConfig] = Field(default_factory=dict)


class ReuseRules(BaseModel):
    """Rules that surface opportunities to consolidate duplicated logic across models.
    Targets the copy-paste redundancy common in legacy ETL migrations."""
    enabled: bool = True
    rules: dict[str, RuleConfig] = Field(default_factory=dict)


class AIProviderConfig(BaseModel):
    enabled: bool = False
    api_key_env_var: str | None = None
    base_url: str | None = None
    models: list[str] = Field(default_factory=list)


class AIReviewRules(BaseModel):
    enabled: bool = False
    provider: AIProvider = AIProvider.ANTHROPIC
    model: str = "claude-sonnet-4-20250514"
    max_tokens_per_review: int = 4096
    anthropic: AIProviderConfig = Field(default_factory=lambda: AIProviderConfig())
    openai: AIProviderConfig = Field(default_factory=lambda: AIProviderConfig())
    gemini: AIProviderConfig = Field(default_factory=lambda: AIProviderConfig())
    rules: dict[str, RuleConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_primary_model(self) -> "AIReviewRules":
        """Maintain backwards compatibility with the legacy provider/model fields."""
        primary = self.get_provider_config(self.provider)
        if self.model and self.model not in primary.models:
            primary.models.insert(0, self.model)
        elif primary.models:
            self.model = primary.models[0]
        return self

    def get_provider_config(self, provider: AIProvider) -> AIProviderConfig:
        return getattr(self, provider.value)

    def enabled_providers(self) -> list[AIProvider]:
        explicitly_enabled = [
            provider for provider in AIProvider if self.get_provider_config(provider).enabled
        ]
        if explicitly_enabled:
            return explicitly_enabled
        return [self.provider]


class CustomRule(BaseModel):
    name: str
    type: str  # "regex" | "yaml_key_exists"
    severity: Severity = Severity.WARNING
    description: str = ""
    pattern: str | None = None
    file_glob: str | None = None
    key_path: str | None = None
    suggestion: str | None = None


class DbtCloudConfig(BaseModel):
    enabled: bool = False
    account_id: int | None = None
    environment_id: int | None = None
    api_base_url: str = "https://cloud.getdbt.com"
    discovery_api_url: str = "https://metadata.cloud.getdbt.com/graphql"
    state_type: str = "applied"
    include_catalog: bool = True
    include_execution_info: bool = True

    @model_validator(mode="after")
    def apply_env_defaults(self) -> "DbtCloudConfig":
        """Fill unset fields from environment variables (e.g. from .env)."""
        import os

        if self.account_id is None:
            raw = os.environ.get("DBT_CLOUD_ACCOUNT_ID")
            if raw:
                self.account_id = int(raw)

        if self.environment_id is None:
            raw = os.environ.get("DBT_CLOUD_ENVIRONMENT_ID")
            if raw:
                self.environment_id = int(raw)

        if os.environ.get("DBT_CLOUD_URL") and self.api_base_url == "https://cloud.getdbt.com":
            self.api_base_url = os.environ["DBT_CLOUD_URL"].rstrip("/")

        if os.environ.get("DBT_CLOUD_DISCOVERY_API_URL") and self.discovery_api_url == "https://metadata.cloud.getdbt.com/graphql":
            self.discovery_api_url = os.environ["DBT_CLOUD_DISCOVERY_API_URL"]

        # Auto-enable when account_id is available and nothing explicitly set enabled=False
        if self.account_id and not self.enabled:
            self.enabled = True

        return self


class ProjectConfig(BaseModel):
    name: str = "dbt Project"
    description: str = ""


class GlobalConfig(BaseModel):
    severity_default: Severity = Severity.WARNING
    fail_on: Severity = Severity.ERROR
    changed_files_only: bool = False
    exclude_paths: list[str] = Field(default_factory=lambda: ["dbt_packages/", "target/"])


class GovernanceConfig(BaseModel):
    version: int = 1
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    dbt_cloud: DbtCloudConfig = Field(default_factory=DbtCloudConfig)
    global_config: GlobalConfig = Field(default_factory=GlobalConfig, alias="global")
    naming: NamingRules = Field(default_factory=NamingRules)
    structure: StructureRules = Field(default_factory=StructureRules)
    testing: TestingRules = Field(default_factory=TestingRules)
    documentation: DocumentationRules = Field(default_factory=DocumentationRules)
    materialization: MaterializationRules = Field(default_factory=MaterializationRules)
    style: StyleRules = Field(default_factory=StyleRules)
    migration: MigrationRules = Field(default_factory=MigrationRules)
    reuse: ReuseRules = Field(default_factory=ReuseRules)
    ai_review: AIReviewRules = Field(default_factory=AIReviewRules)
    custom_rules: list[CustomRule] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    def get_rule_severity(self, category: str, rule_name: str) -> Severity:
        """Get the effective severity for a rule, falling back to global default."""
        category_config = getattr(self, category, None)
        if category_config and hasattr(category_config, "rules"):
            rule = category_config.rules.get(rule_name)
            if rule:
                return rule.severity
        return self.global_config.severity_default

    def is_rule_enabled(self, category: str, rule_name: str) -> bool:
        """Check if a specific rule is enabled."""
        category_config = getattr(self, category, None)
        if category_config is None:
            return False
        if not category_config.enabled:
            return False
        if hasattr(category_config, "rules"):
            rule = category_config.rules.get(rule_name)
            if rule is not None:
                return rule.enabled
        return True

    def is_path_excluded(self, path: str) -> bool:
        """Check if a file path should be excluded from scanning."""
        return any(path.startswith(excl) or f"/{excl}" in path for excl in self.global_config.exclude_paths)


def load_config(path: Path | str | None = None) -> GovernanceConfig:
    """Load governance config from a YAML file, or return defaults."""
    if path is None:
        candidates = [Path(".dbt-governance.yml"), Path(".dbt-governance.yaml")]
        for candidate in candidates:
            if candidate.exists():
                path = candidate
                break

    if path is None:
        return GovernanceConfig()

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return GovernanceConfig()

    return GovernanceConfig.model_validate(raw)


def generate_default_config() -> str:
    """Generate a default .dbt-governance.yml with sensible defaults and comments."""
    return """\
# .dbt-governance.yml
# dbt Governance as Code — configurable best practices enforcement
# Docs: https://github.com/your-org/dbt-governance
version: 1

project:
  name: "My dbt Project"
  description: "Governance rules for our dbt project"

# dbt Cloud configuration (primary data source)
# Set DBT_CLOUD_API_TOKEN env var for authentication
dbt_cloud:
  enabled: false
  # account_id: 12345
  # environment_id: 67890
  # discovery_api_url: "https://metadata.cloud.getdbt.com/graphql"
  # Regions:
  #   NA:   https://metadata.cloud.getdbt.com/graphql
  #   EMEA: https://metadata.emea.dbt.com/graphql
  #   APAC: https://metadata.au.dbt.com/graphql

global:
  severity_default: warning
  fail_on: error
  changed_files_only: false
  exclude_paths:
    - "dbt_packages/"
    - "target/"

naming:
  enabled: true
  rules:
    staging_prefix:
      enabled: true
      severity: error
      pattern: "stg_{source}__{entity}"
    intermediate_prefix:
      enabled: true
      severity: error
      pattern: "int_{entity}_{verb}"
    marts_prefix:
      enabled: true
      severity: error
    source_schema_required:
      enabled: true
      severity: warning
    model_file_matches_name:
      enabled: true
      severity: error

structure:
  enabled: true
  rules:
    staging_refs_source_only:
      enabled: true
      severity: error
    marts_no_source_refs:
      enabled: true
      severity: error
    no_cross_layer_skipping:
      enabled: true
      severity: warning
    max_dag_depth:
      enabled: true
      severity: warning
      max_depth: 8
    max_fanout:
      enabled: true
      severity: warning
      max_children: 10
    no_orphan_models:
      enabled: true
      severity: info
    no_rejoin_patterns:
      enabled: true
      severity: warning
    model_directories_match_layers:
      enabled: true
      severity: error

testing:
  enabled: true
  rules:
    primary_key_test_required:
      enabled: true
      severity: error
    minimum_test_coverage:
      enabled: true
      severity: warning
      min_tests_per_model: 2
    staging_freshness_required:
      enabled: true
      severity: warning
    marts_have_contract:
      enabled: true
      severity: info
    no_disabled_tests:
      enabled: true
      severity: warning

documentation:
  enabled: true
  rules:
    model_description_required:
      enabled: true
      severity: error
      layers:
        - marts
        - intermediate
    column_description_required:
      enabled: true
      severity: warning
      layers:
        - marts
    source_description_required:
      enabled: true
      severity: warning
    schema_yml_exists:
      enabled: true
      severity: error

materialization:
  enabled: true
  rules:
    staging_must_be_view:
      enabled: true
      severity: warning
    incremental_must_have_unique_key:
      enabled: true
      severity: error
    incremental_must_have_on_schema_change:
      enabled: true
      severity: warning

style:
  enabled: true
  rules:
    cte_pattern:
      enabled: true
      severity: warning
    no_hardcoded_schema:
      enabled: true
      severity: error
    no_select_star_in_marts:
      enabled: true
      severity: warning
    final_select_from_named_cte:
      enabled: true
      severity: warning
    refs_in_ctes_not_inline:
      enabled: true
      severity: warning

# ---------------------------------------------------------------------------
# Legacy Migration Rules
# Detects anti-patterns from Talend, Informatica, SSIS, and other ETL tools
# migrated to dbt without restructuring. Forms the "Legacy Migration Report".
# ---------------------------------------------------------------------------
migration:
  enabled: true
  rules:
    no_ref_or_source:
      enabled: true
      severity: error
      description: "Model has no ref()/source() calls — likely a raw ETL SQL migration"
    ddl_statements:
      enabled: true
      severity: error
      description: "Model contains CREATE TABLE / INSERT INTO / TRUNCATE / MERGE statements"
    hardcoded_environment_schema:
      enabled: true
      severity: error
      description: "Model references hardcoded environment schema names (prod., dev., staging., etc.)"
    missing_source_definition:
      enabled: true
      severity: error
      description: "source() is called but the source is not defined in sources.yml"
    no_layering:
      enabled: true
      severity: warning
      description: "Model has no dbt layer structure (no stg_/int_/fct_/dim_ prefix, no layer directory)"

# ---------------------------------------------------------------------------
# Re-use Rules
# Surfaces duplicated logic and consolidation opportunities — targets the
# copy-paste redundancy common when migrating independent ETL pipelines.
# ---------------------------------------------------------------------------
reuse:
  enabled: true
  rules:
    duplicate_source_staging:
      enabled: true
      severity: warning
      description: "Multiple staging models reference the same source table"
    model_similarity_candidates:
      enabled: true
      severity: info
      min_score: 0.72
      max_matches_per_model: 3
      description: "Models with highly similar SQL structure are candidates for consolidation"
    model_similarity_clusters:
      enabled: true
      severity: info
      min_cluster_size: 3
      description: "Groups of highly similar models should converge on one shared intermediate"
    shared_cte_candidates:
      enabled: true
      severity: info
      min_occurrences: 3
      description: "Same CTE name appears in 3+ models — candidate for shared intermediate model"
    multiple_models_from_same_source:
      enabled: true
      severity: warning
      description: "Multiple non-staging models reference the same source directly"
    identical_select_columns:
      enabled: true
      severity: info
      description: "Multiple models select the same columns from the same base — likely copy-pasted"

ai_review:
  enabled: false
  # provider: "anthropic"
  # model: "claude-sonnet-4-20250514"
  # anthropic:
  #   enabled: true
  #   api_key_env_var: "ANTHROPIC_API_KEY"
  #   models:
  #     - "claude-sonnet-4-20250514"
  #     - "claude-opus-4-1-20250805"
  # openai:
  #   enabled: true
  #   api_key_env_var: "OPENAI_API_KEY"
  #   models:
  #     - "gpt-5.4"
  #     - "gpt-5-mini"
  # gemini:
  #   enabled: true
  #   api_key_env_var: "GEMINI_API_KEY"
  #   models:
  #     - "gemini-3.1-pro-preview"
  #     - "gemini-3-flash-preview"
  #     - "gemini-2.5-pro"
  #     - "gemini-2.5-flash"
  # rules:
  #   business_logic_in_staging:
  #     enabled: true
  #     severity: error
"""
