export type Severity = "error" | "warning" | "info";

export type RuleConfig = {
  enabled: boolean;
  severity: Severity;
  description: string;
  [key: string]: unknown;
};

export type RuleCategory = {
  enabled: boolean;
  rules: Record<string, RuleConfig>;
};

export type AiProvider = "claude" | "openai" | "gemini" | "none";

export type GovernanceConfig = {
  version: number;
  project: {
    name: string;
    description: string;
  };
  dbt_cloud: {
    enabled: boolean;
    account_id: number;
    environment_id: number;
    api_base_url: string;
    discovery_api_url: string;
    state_type: "applied" | "definition";
    include_catalog: boolean;
    include_execution_info: boolean;
  };
  ai_provider: {
    provider: AiProvider;
    model: string;
    max_tokens_per_review: number;
  };
  global: {
    severity_default: Severity;
    fail_on: Severity;
    changed_files_only: boolean;
    exclude_paths: string[];
  };
  naming: RuleCategory;
  structure: RuleCategory;
  testing: RuleCategory;
  documentation: RuleCategory;
  materialization: RuleCategory;
  style: RuleCategory;
  migration: RuleCategory;
  reuse: RuleCategory;
};

export type RuleField =
  | { key: string; label: string; type: "text" }
  | { key: string; label: string; type: "number" }
  | { key: string; label: string; type: "list" };

export type RuleDefinition = {
  key: string;
  label: string;
  helper: string;
  fields?: RuleField[];
};

export type CategoryDefinition = {
  key: keyof Pick<
    GovernanceConfig,
    | "naming"
    | "structure"
    | "testing"
    | "documentation"
    | "materialization"
    | "style"
    | "migration"
    | "reuse"
  >;
  title: string;
  description: string;
  accent: string;
  rules: RuleDefinition[];
};

export type CategoryKey = CategoryDefinition["key"];

export const categoryDefinitions: CategoryDefinition[] = [
  {
    key: "naming",
    title: "Naming Rules",
    description: "Lock naming drift down across staging, intermediate, and mart layers.",
    accent: "var(--accent-orange)",
    rules: [
      {
        key: "staging_prefix",
        label: "Staging models follow stg_<source>__<entity>",
        helper: "Catch staging files that break the source-entity contract.",
        fields: [{ key: "pattern", label: "Pattern", type: "text" }]
      },
      {
        key: "intermediate_prefix",
        label: "Intermediate models follow int_<entity>_<verb>",
        helper: "Make transformation intent obvious from filenames.",
        fields: [{ key: "pattern", label: "Pattern", type: "text" }]
      },
      {
        key: "marts_prefix",
        label: "Mart models use fact and dimension prefixes",
        helper: "Keep facts and dimensions visually distinct in the DAG."
      },
      {
        key: "source_schema_required",
        label: "Sources require explicit schema definitions",
        helper: "Avoid implicit source resolution in production."
      },
      {
        key: "model_file_matches_name",
        label: "SQL filenames match model names",
        helper: "Keep file paths and schema metadata aligned."
      }
    ]
  },
  {
    key: "structure",
    title: "Structure Rules",
    description: "Protect layering, lineage shape, and DAG maintainability.",
    accent: "var(--accent-red)",
    rules: [
      {
        key: "staging_refs_source_only",
        label: "Staging models only reference sources",
        helper: "Prevent business logic from drifting into import layers."
      },
      {
        key: "marts_no_source_refs",
        label: "Mart models never reference sources directly",
        helper: "Force marts through governed transformation layers."
      },
      {
        key: "no_cross_layer_skipping",
        label: "Models should not skip layers",
        helper: "Discourage staging-to-mart shortcuts."
      },
      {
        key: "max_dag_depth",
        label: "Limit DAG depth",
        helper: "Keep lineage traversable for debugging and ownership.",
        fields: [{ key: "max_depth", label: "Max depth", type: "number" }]
      },
      {
        key: "max_fanout",
        label: "Limit downstream fanout",
        helper: "Reduce blast radius from overly central nodes.",
        fields: [{ key: "max_children", label: "Max children", type: "number" }]
      },
      {
        key: "no_orphan_models",
        label: "Flag orphan models",
        helper: "Identify models without consumers or exposures."
      },
      {
        key: "no_rejoin_patterns",
        label: "Detect rejoin or diamond patterns",
        helper: "Catch avoidable complexity before it calcifies."
      },
      {
        key: "model_directories_match_layers",
        label: "Model directories match layers",
        helper: "Keep source control layout aligned with semantic layers."
      }
    ]
  },
  {
    key: "testing",
    title: "Testing Rules",
    description: "Raise the floor on contracts, freshness, and model safety.",
    accent: "var(--accent-blue)",
    rules: [
      {
        key: "primary_key_test_required",
        label: "Primary keys require unique and not_null tests",
        helper: "Guarantee a baseline model contract."
      },
      {
        key: "minimum_test_coverage",
        label: "Minimum tests per model",
        helper: "Push teams beyond a single check-box test.",
        fields: [{ key: "min_tests_per_model", label: "Min tests", type: "number" }]
      },
      {
        key: "staging_freshness_required",
        label: "Sources feeding staging require freshness checks",
        helper: "Catch stale ingestion paths before they pollute downstream marts."
      },
      {
        key: "marts_have_contract",
        label: "Mart models should define contracts",
        helper: "Encourage stronger typed interfaces for analytics consumers."
      },
      {
        key: "no_disabled_tests",
        label: "Disabled tests are flagged",
        helper: "Prevent test debt from hiding in schema YAML."
      }
    ]
  },
  {
    key: "documentation",
    title: "Documentation Rules",
    description: "Require just enough metadata that the warehouse stays legible.",
    accent: "var(--accent-green)",
    rules: [
      {
        key: "model_description_required",
        label: "Models require descriptions in key layers",
        helper: "Focus on intermediate and mart layers where intent matters most.",
        fields: [{ key: "layers", label: "Layers", type: "list" }]
      },
      {
        key: "column_description_required",
        label: "Mart columns require descriptions",
        helper: "Help analysts trust exposed business entities.",
        fields: [{ key: "layers", label: "Layers", type: "list" }]
      },
      {
        key: "source_description_required",
        label: "Sources require descriptions",
        helper: "Keep ingestion context close to the source definitions."
      },
      {
        key: "schema_yml_exists",
        label: "Schema YAML exists per model directory",
        helper: "Eliminate undocumented pockets of the repo."
      }
    ]
  },
  {
    key: "materialization",
    title: "Materialization Rules",
    description: "Guide performance choices without surrendering governance.",
    accent: "var(--accent-gold)",
    rules: [
      {
        key: "staging_must_be_view",
        label: "Staging models should be views",
        helper: "Keep import layers light and disposable."
      },
      {
        key: "incremental_must_have_unique_key",
        label: "Incremental models require unique_key",
        helper: "Avoid unsafe merge semantics."
      },
      {
        key: "incremental_must_have_on_schema_change",
        label: "Incremental models should define on_schema_change",
        helper: "Make schema evolution explicit instead of accidental."
      }
    ]
  },
  {
    key: "style",
    title: "SQL Style Rules",
    description: "Enforce dbt-specific SQL discipline that generic linters miss.",
    accent: "var(--accent-violet)",
    rules: [
      {
        key: "cte_pattern",
        label: "Prefer import-then-logical CTE structure",
        helper: "Keep ref() imports visually separated from transformation logic.",
        fields: [{ key: "pattern", label: "Pattern", type: "text" }]
      },
      {
        key: "no_hardcoded_schema",
        label: "No hardcoded schema or database references",
        helper: "Preserve environment portability."
      },
      {
        key: "no_select_star_in_marts",
        label: "No SELECT * in marts",
        helper: "Make marts contract-shaped instead of accidental."
      },
      {
        key: "final_select_from_named_cte",
        label: "Final select should come from a named CTE",
        helper: "Keep model outputs visually intentional."
      },
      {
        key: "refs_in_ctes_not_inline",
        label: "Place ref() calls in import CTEs, not inline joins",
        helper: "Improve readability and diffability."
      }
    ]
  },
  {
    key: "migration",
    title: "Migration Rules",
    description: "Surface anti-patterns carried in from Talend, Informatica, SSIS, and other legacy ETL tools.",
    accent: "var(--accent-brick)",
    rules: [
      {
        key: "no_ref_or_source",
        label: "Models must use ref() or source() — not direct table references",
        helper: "A model with no ref()/source() calls breaks dbt lineage entirely. Classic Talend/Informatica migration symptom."
      },
      {
        key: "ddl_statements",
        label: "No DDL or DML statements (CREATE TABLE, INSERT INTO, MERGE, TRUNCATE)",
        helper: "dbt manages DDL via materializations. These statements indicate a procedural ETL job was pasted directly."
      },
      {
        key: "hardcoded_environment_schema",
        label: "No hardcoded environment schema names (prod., dev., staging., edw.)",
        helper: "Hardcoded schemas break when the same model runs in dev or CI. Use source() and ref() instead."
      },
      {
        key: "missing_source_definition",
        label: "source() calls must have a corresponding sources.yml entry",
        helper: "Orphaned source() calls mean lineage is incomplete and freshness checks will never run."
      },
      {
        key: "no_layering",
        label: "Every model must belong to a recognizable dbt layer",
        helper: "Models without stg_/int_/fct_/dim_ prefixes or a layer directory were likely migrated as monolithic ETL jobs."
      }
    ]
  },
  {
    key: "reuse",
    title: "Re-use Rules",
    description: "Find redundant pipelines and consolidation opportunities — the copy-paste problem in legacy migrations.",
    accent: "var(--accent-teal)",
    rules: [
      {
        key: "duplicate_source_staging",
        label: "Each source table should have exactly one staging model",
        helper: "Multiple staging models on the same source creates divergent logic. One staging model, many consumers via ref()."
      },
      {
        key: "shared_cte_candidates",
        label: "Repeated CTE names across many models — extract to a shared intermediate",
        helper: "The same CTE name in 3+ models is a strong signal of copy-pasted logic that belongs in one shared model.",
        fields: [{ key: "min_occurrences", label: "Min occurrences to flag", type: "number" }]
      },
      {
        key: "multiple_models_from_same_source",
        label: "Non-staging models should not reference the same source directly",
        helper: "Two intermediate or mart models hitting the same raw source table means staging was skipped for both."
      },
      {
        key: "identical_select_columns",
        label: "Identical column selections from the same base should be a shared model",
        helper: "Multiple models selecting the same columns from the same upstream is a high-confidence copy-paste signal."
      }
    ]
  }
];

export const defaultGovernanceConfig: GovernanceConfig = {
  version: 1,
  project: {
    name: "Acme Analytics",
    description: "Central governance baseline for all dbt Cloud projects."
  },
  dbt_cloud: {
    enabled: true,
    account_id: 0,
    environment_id: 0,
    api_base_url: "https://cloud.getdbt.com",
    discovery_api_url: "https://metadata.cloud.getdbt.com/graphql",
    state_type: "applied",
    include_catalog: true,
    include_execution_info: true
  },
  ai_provider: {
    provider: "claude",
    model: "claude-sonnet-4-6",
    max_tokens_per_review: 4096
  },
  global: {
    severity_default: "warning",
    fail_on: "error",
    changed_files_only: false,
    exclude_paths: ["dbt_packages/", "target/", "macros/internal/"]
  },
  naming: {
    enabled: true,
    rules: {
      staging_prefix: {
        enabled: true,
        severity: "error",
        pattern: "stg_{source}__{entity}",
        description: "Staging models must follow stg_<source>__<entity> naming"
      },
      intermediate_prefix: {
        enabled: true,
        severity: "error",
        pattern: "int_{entity}_{verb}",
        description: "Intermediate models must follow int_<entity>_<verb> naming"
      },
      marts_prefix: {
        enabled: true,
        severity: "error",
        patterns: { facts: "fct_{entity}", dimensions: "dim_{entity}", other: "{entity}" },
        description: "Mart models use fct_ or dim_ prefixes for facts and dimensions"
      },
      source_schema_required: {
        enabled: true,
        severity: "warning",
        description: "All sources must have an explicit schema defined"
      },
      model_file_matches_name: {
        enabled: true,
        severity: "error",
        description: "SQL filename must match the model name defined in schema YAML"
      }
    }
  },
  structure: {
    enabled: true,
    rules: {
      staging_refs_source_only: {
        enabled: true,
        severity: "error",
        description: "Staging models may only ref() sources, not other models"
      },
      marts_no_source_refs: {
        enabled: true,
        severity: "error",
        description: "Mart models must not directly reference sources"
      },
      no_cross_layer_skipping: {
        enabled: true,
        severity: "warning",
        description: "Models should not skip layers (e.g., marts referencing staging directly without intermediate)"
      },
      max_dag_depth: {
        enabled: true,
        severity: "warning",
        max_depth: 8,
        description: "No model should have more than N upstream ancestors"
      },
      max_fanout: {
        enabled: true,
        severity: "warning",
        max_children: 10,
        description: "No model should be referenced by more than N downstream models"
      },
      no_orphan_models: {
        enabled: true,
        severity: "info",
        description: "Every model should have at least one downstream dependency or be an exposure endpoint"
      },
      no_rejoin_patterns: {
        enabled: true,
        severity: "warning",
        description: "Detect models that rejoin to a table they previously derived from"
      },
      model_directories_match_layers: {
        enabled: true,
        severity: "error",
        directories: {
          staging: "models/staging/",
          intermediate: "models/intermediate/",
          marts: "models/marts/"
        },
        description: "Models must live in the directory matching their layer"
      }
    }
  },
  testing: {
    enabled: true,
    rules: {
      primary_key_test_required: {
        enabled: true,
        severity: "error",
        description: "Every model must have a unique + not_null test on its primary key"
      },
      minimum_test_coverage: {
        enabled: true,
        severity: "warning",
        min_tests_per_model: 2,
        description: "Every model must have at least N tests"
      },
      staging_freshness_required: {
        enabled: true,
        severity: "warning",
        description: "All sources feeding staging models must have freshness checks"
      },
      marts_have_contract: {
        enabled: true,
        severity: "info",
        description: "Mart models should define a model contract for column type enforcement"
      },
      no_disabled_tests: {
        enabled: true,
        severity: "warning",
        description: "Tests should not be disabled"
      }
    }
  },
  documentation: {
    enabled: true,
    rules: {
      model_description_required: {
        enabled: true,
        severity: "error",
        layers: ["marts", "intermediate"],
        description: "Models in specified layers must have a description in schema YAML"
      },
      column_description_required: {
        enabled: true,
        severity: "warning",
        layers: ["marts"],
        description: "All columns in mart models must have descriptions"
      },
      source_description_required: {
        enabled: true,
        severity: "warning",
        description: "All sources must have a description"
      },
      schema_yml_exists: {
        enabled: true,
        severity: "error",
        description: "Every model directory must contain a corresponding schema YAML file"
      }
    }
  },
  materialization: {
    enabled: true,
    rules: {
      staging_must_be_view: {
        enabled: true,
        severity: "warning",
        description: "Staging models should be materialized as views"
      },
      incremental_must_have_unique_key: {
        enabled: true,
        severity: "error",
        description: "Incremental models must specify a unique_key"
      },
      incremental_must_have_on_schema_change: {
        enabled: true,
        severity: "warning",
        description: "Incremental models should define on_schema_change strategy"
      }
    }
  },
  style: {
    enabled: true,
    rules: {
      cte_pattern: {
        enabled: true,
        severity: "warning",
        pattern: "import_then_logical",
        description: "Models should use import CTEs followed by logical CTEs"
      },
      no_hardcoded_schema: {
        enabled: true,
        severity: "error",
        description: "SQL must not contain hardcoded schema or database references"
      },
      no_select_star_in_marts: {
        enabled: true,
        severity: "warning",
        description: "Mart models should not use SELECT *"
      },
      final_select_from_named_cte: {
        enabled: true,
        severity: "warning",
        description: "The final SELECT in a model should reference a named CTE"
      },
      refs_in_ctes_not_inline: {
        enabled: true,
        severity: "warning",
        description: "ref() calls should be in import CTEs, not inline in joins"
      }
    }
  },
  migration: {
    enabled: true,
    rules: {
      no_ref_or_source: {
        enabled: true,
        severity: "error",
        description: "Model has no ref()/source() calls — likely a raw ETL SQL migration"
      },
      ddl_statements: {
        enabled: true,
        severity: "error",
        description: "Model contains DDL/DML statements (CREATE TABLE, INSERT INTO, TRUNCATE, MERGE)"
      },
      hardcoded_environment_schema: {
        enabled: true,
        severity: "error",
        description: "SQL references hardcoded environment schema names (prod., dev., staging., edw., etc.)"
      },
      missing_source_definition: {
        enabled: true,
        severity: "error",
        description: "source() is called but the source is not defined in any sources.yml"
      },
      no_layering: {
        enabled: true,
        severity: "warning",
        description: "Model has no dbt layer structure — no stg_/int_/fct_/dim_ prefix and no layer directory"
      }
    }
  },
  reuse: {
    enabled: true,
    rules: {
      duplicate_source_staging: {
        enabled: true,
        severity: "warning",
        description: "Multiple staging models reference the same source table"
      },
      shared_cte_candidates: {
        enabled: true,
        severity: "info",
        min_occurrences: 3,
        description: "Same CTE name appears in 3+ models — candidate for a shared intermediate model"
      },
      multiple_models_from_same_source: {
        enabled: true,
        severity: "warning",
        description: "Multiple non-staging models reference the same source table directly"
      },
      identical_select_columns: {
        enabled: true,
        severity: "info",
        description: "Multiple models select the same column set from the same base — likely copy-pasted"
      }
    }
  }
};

const severityOrder: Severity[] = ["error", "warning", "info"];

function quoteString(value: string): string {
  return `"${value.replaceAll('"', '\\"')}"`;
}

function serializeYamlValue(value: unknown, indent = 0): string[] {
  const padding = "  ".repeat(indent);

  if (Array.isArray(value)) {
    return value.flatMap((entry) => {
      if (typeof entry === "string" || typeof entry === "number" || typeof entry === "boolean") {
        return [`${padding}- ${typeof entry === "string" ? quoteString(entry) : String(entry)}`];
      }
      return [`${padding}-`, ...serializeYamlValue(entry, indent + 1)];
    });
  }

  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, nested]) => {
      if (
        nested === null ||
        typeof nested === "string" ||
        typeof nested === "number" ||
        typeof nested === "boolean"
      ) {
        const rendered =
          typeof nested === "string" ? quoteString(nested) : nested === null ? "null" : String(nested);
        return [`${padding}${key}: ${rendered}`];
      }
      return [`${padding}${key}:`, ...serializeYamlValue(nested, indent + 1)];
    });
  }

  if (typeof value === "string") {
    return [`${padding}${quoteString(value)}`];
  }

  return [`${padding}${String(value)}`];
}

export function generateYaml(config: GovernanceConfig): string {
  return serializeYamlValue(config).join("\n") + "\n";
}

export function generateReviewMd(config: GovernanceConfig): string {
  const grouped = new Map<Severity, string[]>(severityOrder.map((severity) => [severity, []]));

  for (const category of categoryDefinitions) {
    const categoryState = config[category.key];
    if (!categoryState.enabled) continue;
    for (const rule of Object.values(categoryState.rules)) {
      if (!rule.enabled) continue;
      grouped.get(rule.severity)?.push(rule.description);
    }
  }

  const linesFor = (severity: Severity): string[] => {
    const items = grouped.get(severity) ?? [];
    return items.length > 0 ? items.map((item) => `- ${item}`) : ["- None configured"];
  };

  return [
    "# dbt Governance Review Rules",
    "",
    "<!-- Auto-generated by Central Governance -->",
    "",
    `Project: ${config.project.name}`,
    "",
    "Apply these standards during code review for changed dbt files. Prioritize errors, then warnings.",
    "",
    "## Always Check (Error)",
    ...linesFor("error"),
    "",
    "## Check with Warnings (Warning)",
    ...linesFor("warning"),
    "",
    "## Optional Improvements (Info)",
    ...linesFor("info"),
    "",
    "## Scope",
    `- Skip these paths: ${config.global.exclude_paths.join(", ")}`,
    config.global.changed_files_only
      ? "- Focus on changed files only"
      : "- Review the full affected dbt surface, not only changed files"
  ].join("\n");
}

export function generateClaudeMd(config: GovernanceConfig): string {
  const naming = config.naming.rules;
  const martsPatterns = naming.marts_prefix.patterns as Record<string, string>;
  const layerDirectories = config.structure.rules.model_directories_match_layers
    .directories as Record<string, string>;

  const migrationEnabled = config.migration.enabled &&
    Object.values(config.migration.rules).some((r) => r.enabled);
  const reuseEnabled = config.reuse.enabled &&
    Object.values(config.reuse.rules).some((r) => r.enabled);

  return [
    `# dbt Project: ${config.project.name}`,
    "",
    "<!-- Auto-generated by Central Governance -->",
    "",
    config.project.description,
    "",
    "## Review Context",
    "- This repository uses dbt governance as code. Apply these standards when reviewing SQL, YAML, and model structure changes.",
    config.dbt_cloud.enabled
      ? `- Primary metadata source: dbt Cloud environment \`${config.dbt_cloud.environment_id}\` using \`${config.dbt_cloud.state_type}\` state.`
      : "- Primary metadata source: local manifest fallback mode.",
    ...(migrationEnabled
      ? [
          "",
          "## Legacy Migration Checks",
          "- Flag any model with no ref() or source() calls — this breaks dbt lineage.",
          "- Flag CREATE TABLE, INSERT INTO, TRUNCATE, or MERGE statements — use materializations instead.",
          "- Flag hardcoded schema/database references (prod., dev., staging., edw.) — use source() or ref().",
          "- Flag models without stg_/int_/fct_/dim_ naming or layer directory — they were likely migrated as monolithic ETL jobs."
        ]
      : []),
    ...(reuseEnabled
      ? [
          "",
          "## Re-use Checks",
          "- Flag when two or more models appear to be staging the same source table independently.",
          "- Flag identical or near-identical CTE blocks across models — suggest extracting to a shared intermediate.",
          "- Note any obvious consolidation opportunities when reviewing multiple related models in the same PR."
        ]
      : []),
    "",
    "## Architecture Expectations",
    "- Preferred layer progression: staging → intermediate → marts.",
    ...Object.entries(layerDirectories).map(([layer, path]) => `- ${capitalize(layer)} models belong under \`${path}\`.`),
    "",
    "## Naming Conventions",
    `- Staging: ${String(naming.staging_prefix.pattern)}`,
    `- Intermediate: ${String(naming.intermediate_prefix.pattern)}`,
    `- Marts: ${Object.entries(martsPatterns)
      .map(([name, pattern]) => `${name}=${pattern}`)
      .join(", ")}`,
    "",
    "## Enforcement Notes",
    `- CI fails on \`${config.global.fail_on}\` severity or higher.`,
    `- Ignore these paths during review unless explicitly requested: ${config.global.exclude_paths.join(", ")}`,
    "- Preserve model tests, descriptions, and incremental safety guards when editing governed models."
  ].join("\n");
}

export function cloneConfig(config: GovernanceConfig): GovernanceConfig {
  return JSON.parse(JSON.stringify(config)) as GovernanceConfig;
}

export function countEnabledRules(config: GovernanceConfig): number {
  return categoryDefinitions.reduce((total, category) => {
    const categoryState = config[category.key];
    return total + Object.values(categoryState.rules).filter((rule) => rule.enabled).length;
  }, 0);
}

export function severityBreakdown(config: GovernanceConfig): Record<Severity, number> {
  const counts: Record<Severity, number> = { error: 0, warning: 0, info: 0 };
  for (const category of categoryDefinitions) {
    for (const rule of Object.values(config[category.key].rules)) {
      if (rule.enabled) {
        counts[rule.severity] += 1;
      }
    }
  }
  return counts;
}

export function isCloudConfigured(config: GovernanceConfig): boolean {
  return (
    config.dbt_cloud.enabled &&
    config.dbt_cloud.account_id > 0 &&
    config.dbt_cloud.environment_id > 0
  );
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
