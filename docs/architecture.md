# dbt Governance as Code — Architecture

This document outlines how the application works, who uses it, and how the pieces fit together. The primary users are **central platform / architecture teams** (Central Governance teams) who define standards and need a simple way to enforce them across existing dbt Cloud projects.

---

## User Persona: The Central Governance Team

- **Who**: Central platform / architecture team (e.g., 5–15 people)
- **Goal**: Establish and enforce dbt best practices across 10–100+ projects and developers
- **Pain**: Today they write docs, do manual reviews, and hope people follow standards
- **Need**: Configure rules in minutes, apply them immediately to any project, and integrate with existing workflows (CI, Code Review)

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         dbt Governance as Code                                       │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐  │
│   │ Central Gov  │────▶│  Governance  │────▶│   Scanner    │────▶│ Code Review  │  │
│   │  UI (Web)    │     │    Config    │     │  (CLI/API)   │     │  Integration │  │
│   └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘  │
│         │                      │                      │                    │         │
│         ▼                      ▼                      ▼                    ▼         │
│   Checkboxes,            .dbt-governance.yml    dbt Cloud APIs       REVIEW.md      │
│   inputs, download       (version controlled)   + manifest.json      CLAUDE.md      │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## How This Differs from Existing Tools

Several tools address adjacent problems in the dbt ecosystem. None of them were designed to serve Central Governance teams managing standards across many projects, and none cover the full surface area this tool addresses.

### Comparison Matrix

| Capability | dbt Governance as Code | dbt_project_evaluator | SQLFluff | Elementary | dbt Cloud native |
|---|---|---|---|---|---|
| **No dbt install / warehouse needed** | ✅ | ❌ Requires `dbt run` | ✅ | ❌ Requires `dbt run` | ✅ |
| **Queries dbt Cloud APIs directly** | ✅ Discovery + Admin API | ❌ | ❌ | ❌ | ✅ (read-only) |
| **Runs in CI without warehouse** | ✅ | ❌ | ✅ (syntax only) | ❌ | ❌ |
| **Configurable via UI (non-technical users)** | ✅ Central Governance UI | ❌ Hardcoded SQL | ❌ | ❌ | ❌ |
| **One config → scan + Code Review** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **DAG structure enforcement** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Legacy migration detection** | ✅ Dedicated report | ❌ | ❌ | ❌ | ❌ |
| **Re-use / redundancy detection** | ✅ Dedicated report | ❌ | ❌ | ❌ | ❌ |
| **Naming convention enforcement** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **SQL style rules** | ✅ | ❌ | ✅ (deep) | ❌ | ❌ |
| **Test coverage enforcement** | ✅ | ✅ | ❌ | ✅ (monitoring) | ❌ |
| **AI semantic review** | ✅ Phase 2 (REVIEW.md now) | ❌ | ❌ | ❌ | ❌ |
| **SARIF / inline PR annotations** | ✅ | ❌ | ✅ | ❌ | ❌ |
| **Cross-project governance** | ✅ (one config, many projects) | ❌ | ❌ | ❌ | ❌ |

### Tool-by-Tool Breakdown

#### dbt_project_evaluator (dbt Labs)

The closest tool to this one in intent — it evaluates whether a dbt project follows best practices. However, it has fundamental design constraints that make it unsuitable for Central Governance teams:

- **Requires running dbt.** The tool installs as a dbt package and runs as dbt models. This means it requires a fully functional dbt environment with warehouse credentials, a complete `dbt run`, and the target schema populated. It cannot run in CI without connecting to a warehouse.
- **Rules are hardcoded SQL.** Modifying or disabling rules means forking the package or writing override macros. There is no config file, no checkboxes, no way for a non-developer to adjust thresholds.
- **No legacy migration detection.** It was not designed to surface ETL migration debt — hardcoded schemas, DDL statements, missing `ref()` usage, or pipeline redundancy.
- **No re-use detection.** It cannot identify duplicate staging logic or pipelines that should share an intermediate model.
- **No Code Review integration.** Results exist only as dbt model outputs; there is no connection to Claude Code Review, REVIEW.md, or SARIF.

**Summary:** dbt_project_evaluator is a good starting point for teams already running dbt, but it cannot operate at the Central Governance level — it requires a warehouse, isn't configurable without code changes, and doesn't cover migration debt or re-use.

#### SQLFluff

A SQL linter and formatter. It handles syntax, style, and formatting well, but it operates on SQL files in isolation — it has no awareness of dbt DAG structure, model layers, test coverage, or dbt-specific patterns.

- Cannot check DAG structure (layer violations, source refs in marts, orphan models).
- Cannot check test coverage or documentation completeness.
- Cannot detect legacy migration anti-patterns (it sees DDL as valid SQL).
- No dbt Cloud API integration; no governance scoring.

**Summary:** SQLFluff is a good complement for SQL style enforcement (and this tool deliberately avoids duplicating its syntax rules), but it is not a governance tool.

#### Elementary

Elementary focuses on **data observability** — monitoring data freshness, schema changes, anomalies, and test failures over time. It is not a governance or standards enforcement tool.

- Monitors what is running in production; does not enforce how models are built.
- Requires dbt to run; integrates as a dbt package.
- No naming convention, DAG structure, or migration debt checks.
- Not designed for pre-merge CI enforcement.

**Summary:** Elementary answers "is my data pipeline healthy right now?" This tool answers "is my dbt project built correctly?" They address different jobs and are complementary.

#### dbt Cloud Native Controls

dbt Cloud provides some built-in governance features (model contracts, access modifiers, groups, CI job triggers), but these are project-level controls configured inside the dbt project itself — not a layer that Central Governance teams can configure and push across projects.

- No cross-project rule enforcement from a central config.
- No static analysis of SQL files; cannot detect hardcoded schemas or DDL.
- No re-use or legacy migration detection.
- No Central Governance UI for non-technical configuration.

**Summary:** dbt Cloud's native controls are the enforcement mechanisms this tool can integrate with (e.g., checking whether `contract_enforced: true` is set). They are not a replacement for a static analysis and governance layer.

### Why This Tool Exists

The gap is: **a Central Governance team needs to define standards once and push them across every project, without requiring each project team to install dependencies, run a warehouse, or write code.** That is the design constraint that every existing tool fails to meet — and the primary reason this tool was built.

---

## The Hybrid Approach

The system has two complementary enforcement layers:

| Layer | What It Does | When It Runs | Data Source |
|-------|--------------|--------------|-------------|
| **Deterministic Scanner** | Runs 30+ structural rules (naming, DAG, tests, docs, materialization, SQL style, migration, re-use) | CI pre-merge, on-demand | dbt Cloud Discovery API or local manifest |
| **Code Review (Claude)** | Semantic checks (business logic in staging, description–code mismatch, incremental correctness) | On every PR via GitHub/GitLab/Azure DevOps | REVIEW.md + CLAUDE.md generated from governance config |

**Flow:**
1. Platform team configures rules in the Central Governance UI (or edits YAML directly).
2. Config saved as `.dbt-governance.yml` and committed to the dbt repo alongside `REVIEW.md` and `CLAUDE.md`.
3. **Scanner** runs against the dbt project via CI (no warehouse needed — uses dbt Cloud Discovery API or manifest.json).
4. **Claude Code Review** reads `REVIEW.md` and `CLAUDE.md` and applies the rules on every PR.

The same standards drive both the deterministic scan and the AI-powered review.

---

## Real Operator Experience

Live testing changed one important design assumption: **the best PR experience comes from local parse mode, not cloud mode**.

### When to use Cloud mode

Use `dbt-governance scan --cloud` when the goal is to validate a real dbt Cloud account and environment:

- Confirm the service token works
- Confirm Discovery/Admin API access works
- Confirm a real sandbox or production environment can be scanned
- Confirm an AI provider can run against real metadata

This is the best path for sandbox validation, account onboarding, and on-demand audits.

### When to use Local parse mode

Use local mode in CI for pull requests:

1. CI checks out the PR branch
2. CI runs `dbt parse`
3. CI runs `dbt-governance scan --local --manifest target/manifest.json --project-dir . --changed-only --github-annotate` with `GITHUB_SHA` overridden to the PR head SHA

Why this is the best PR experience:

- New models added in the branch appear in the fresh manifest
- Changed SQL/YAML in the checked-out repo is read directly from disk
- GitHub Check annotations are attached to the current commit SHA
- CI does not depend on deployed dbt Cloud environment state lagging behind the branch

### Recommended operating split

- **Cloud mode**: live environment validation, sandbox scanning, production audits
- **Local mode**: PR validation, changed-files-only scans, fixture-repo automation

---

## Frontend Architecture: Central Governance UI

### Purpose
Give platform teams a **zero-YAML** way to define and tweak governance rules. Checkboxes, dropdowns, and simple inputs — no need to understand the config schema.

### Implementation
Static Next.js app (`hub/`). No backend required — all config generation happens client-side. Platform team configures in browser, downloads three files, commits them to the dbt repo.

---

## End-to-End User Flow

### Flow 1: Set Up Standards (First Time)

```
1. Open the Central Governance UI (cd hub && npm run dev)
2. Connect dbt Cloud (API token, account ID, environment ID) via Settings
3. Toggle rules on/off, set severities, adjust numeric thresholds
4. Download .dbt-governance.yml, REVIEW.md, and CLAUDE.md
5. Commit all three files to the root of the dbt project repo
6. Add CI workflow (GitHub Actions / GitLab / Azure DevOps) — see README
```

### Flow 2: Apply to an Existing Project

```
1. Add .dbt-governance.yml to the project (downloaded from Central Governance UI)
2. In project's CI:
   - pip install dbt-governance
   - dbt parse
   - dbt-governance scan --local --manifest target/manifest.json --project-dir . --changed-only --github-annotate --output sarif --output-file results.sarif
3. GitHub Check annotations appear on the PR commit
4. Upload SARIF for code scanning visibility
4. Commit REVIEW.md and CLAUDE.md — Claude Code Review discovers them automatically
5. Every PR now gets:
   - Deterministic scan (naming, structure, tests, docs, migration, re-use)
   - AI semantic review (business logic, descriptions, incremental patterns)
```

### Flow 3: Validate a Live Sandbox

```bash
# Best for validating real dbt Cloud connectivity and environment scanning
dbt-governance cloud test-connection
dbt-governance scan --cloud
dbt-governance scan --cloud --with-ai
```

### Flow 4: Point at a Different Project

```bash
# Same config pattern, different environment — change the config or env vars
DBT_CLOUD_ACCOUNT_ID=123456 \
DBT_CLOUD_ENVIRONMENT_ID=789012 \
dbt-governance scan --cloud
```

---

## Code Review Integration

### What gets generated

**REVIEW.md** — tells Claude Code Review what to enforce on every PR. Auto-generated from `.dbt-governance.yml` via:
```bash
dbt-governance generate review-md
```

**CLAUDE.md** — project context automatically read by Claude Code when developers run `claude` in the repo. Auto-generated via:
```bash
dbt-governance generate claude-md
```

Both files are committed to the **root** of the dbt project repo. Claude Code discovers `CLAUDE.md` automatically; no extra config needed.

---

## Re-use Detection: Finding Redundant Pipelines

Re-use detection is one of the two core jobs this tool was built to do. It is distinct from general best practices enforcement — it is specifically about identifying where multiple models are independently doing the same work and surfacing those models as candidates for consolidation into a shared intermediate model.

### The Problem It Solves

When enterprises migrate independent ETL pipelines to dbt, each pipeline team typically migrates their own work in isolation. They are not aware of what other teams have already built. The result is a dbt project where:

- Five different staging models all read from `raw.orders` and rename the same 12 columns in slightly different ways.
- Three mart models each contain an identical CTE that joins `customers` to `addresses` — copy-pasted from team to team.
- Two teams built `int_payments_cleaned` independently, with slightly different logic for the same business concept.
- A source table is staged four times because nobody knew the first staging model existed.

This creates two categories of risk:

1. **Divergence risk.** When the upstream source changes, only some of the duplicate models get updated. Downstream consumers of the stale copies start producing wrong answers.
2. **Maintenance cost.** Every fix, every schema change, every new column has to be replicated manually across all the copies. Teams spend time making the same change in four places.

The re-use detection rules surface this before it accumulates further and produce an actionable consolidation report: here are the models, here is the duplicated logic, here is what a shared model should look like.

### What "Re-use" Means Concretely

Re-use detection is not about code style. It is about identifying structural duplication at the model level:

| Pattern | Description | Candidate Fix |
|---|---|---|
| **Model-level similarity scoring** | Two models have highly similar inputs, selected columns, joins, filters, and aggregation shape even if their CTE names differ | Extract the shared logic into a reusable intermediate and keep only the genuinely divergent downstream logic in each model |
| **Similarity clusters** | Three or more models form a connected similarity group, indicating one shared intermediate should replace several parallel branches | Build a single shared intermediate for the common logic, then reduce each cluster member to only its unique downstream logic |
| **Duplicate source staging** | Two or more staging models both reference the same source table as their primary input | Delete the duplicates; all downstream models should `ref()` the canonical staging model |
| **Duplicate CTE names across models** | The same CTE name (e.g., `customers`, `paid_orders`, `active_subscriptions`) appears in 3+ separate models with similar structure | Extract the CTE into a shared intermediate model; downstream models `ref()` it |
| **Multiple non-staging models reading the same source** | Mart or intermediate models bypass the staging layer and read directly from the same raw source table | Enforce a single staging model as the entry point; marts should `ref()` staging, not `source()` directly |
| **Identical column selections from the same base** | Multiple models select the same set of columns from the same upstream model or source | Candidate for a shared base model that both reference |

### How the Rules Work

The re-use rules operate on the `ManifestData` graph produced by the scanner:

**`reuse.model_similarity_candidates`**
Builds a structural profile for each model using normalized SQL parsing: inputs, selected columns, joins, filters, grouping, aggregates, and CTE names. It then computes a weighted similarity score between same-layer models. Pairs above a configurable threshold are surfaced as consolidation candidates even when they do not use the same CTE names or formatting. Each finding now carries structured pairwise details: the similarity score, a confidence band (`high`, `medium`, `low`), the paired model, the shared inputs/columns/aggregates/filters, and a suggested shared intermediate name.

**`reuse.model_similarity_clusters`**
Builds a similarity graph from the pairwise model matches, then finds connected groups of models that all overlap strongly enough to be treated as one consolidation opportunity. Instead of asking a governance team to look at six separate pairwise findings, it can now say "these 4 models form one reuse cluster." Each finding includes the cluster members, average and peak similarity, the strongest example links, common inputs/columns/filters, and a suggested shared intermediate model name.

**`reuse.duplicate_source_staging`**
Iterates all staging models and builds a map of `source_table → [staging_models]`. Any source table that maps to more than one staging model is flagged. Each duplicate staging model gets a violation with a suggestion identifying the canonical model and the models that should be removed.

**`reuse.shared_cte_candidates`**
Iterates all SQL files and extracts top-level CTE names via `sqlglot`. Builds a map of `cte_name → [models_containing_it]`. Any CTE name appearing in `min_occurrences` or more models (default: 3) is flagged. The violation names all models that share the CTE and suggests extracting it into a shared intermediate.

**`reuse.multiple_models_from_same_source`**
Scans the DAG for `source()` references. Any source node that has more than one non-staging model as a direct consumer is flagged. The intent: non-staging models should consume from a staging model, not compete to read the same source independently.

**`reuse.identical_select_columns`**
Groups models by their `(upstream_model, selected_columns)` signature. When two or more models select an identical set of columns from the same upstream model, they are flagged as candidates for a shared base.

### The Re-use Report

In terminal output, re-use violations appear in their own section alongside the Legacy Migration Report. Each violation includes:

- The rule that triggered and the models involved
- A description of the specific duplication pattern
- For similarity matches, the confidence band and the paired model
- For similarity clusters, the full model group, average similarity, and suggested shared intermediate
- A concrete suggestion: which model to keep, which to remove, or what the shared intermediate should be named and what it should contain

In JSON output, both pairwise and cluster similarity findings now include a structured `details` object so downstream tooling can rank or visualize the strongest consolidation opportunities without parsing freeform text. The scan result also includes a dedicated `reuse_report` section that orders cluster recommendations first and strongest remaining pairs second, producing an explicit remediation queue instead of a flat list of findings. The Hub UI uses these details to render confidence pills, paired-model context, cluster membership, strongest example links, and one-click tuning presets for conservative, balanced, or broad discovery scans. Governance score contribution is weighted at 8% — lower than structural rules, because re-use issues are an improvement opportunity rather than a correctness defect, but enough to move the score meaningfully when a project has significant pipeline redundancy.

When teams need a handoff artifact rather than JSON, the scanner can also generate `REUSE_REPORT.md` from a live scan. This markdown report mirrors the ranked `reuse_report` structure: clusters first, strongest remaining pairs second, with suggested shared intermediates and supporting overlap signals. It now begins with an executive summary oriented at governance leads: overall remediation risk, number of high-priority actions, and the top consolidation moves to staff first. It is designed to be handed directly to a domain team as a remediation worklist after leadership triage.

### Relationship to the Legacy Migration Report

Legacy migration detection and re-use detection are related but distinct:

- **Migration rules** ask: "Was this model ported correctly from the ETL tool?" They look for evidence that a human copy-pasted raw SQL without restructuring it as a dbt model (no `ref()`, DDL statements, hardcoded schemas).
- **Re-use rules** ask: "Are multiple models independently doing the same work?" They look for structural duplication in an otherwise-functional dbt project — models that use `ref()` correctly but happen to duplicate each other's logic.

A project migrated from Talend will typically have both problems: migration defects *and* redundant pipelines. In practice, re-use violations often appear at a higher rate in recently-migrated projects, because each ETL job was migrated in isolation without a consolidation step. The two reports together give a complete picture of migration debt.

### Configuration

```yaml
reuse:
  enabled: true
  rules:
    model_similarity_candidates:
      enabled: true
      severity: info
      min_score: 0.72        # Weighted structural similarity threshold
      max_matches_per_model: 3

    model_similarity_clusters:
      enabled: true
      severity: info
      min_cluster_size: 3   # Minimum group size before emitting a cluster recommendation

    duplicate_source_staging:
      enabled: true
      severity: warning

    shared_cte_candidates:
      enabled: true
      severity: info
      min_occurrences: 3    # How many models must share a CTE name before flagging

    multiple_models_from_same_source:
      enabled: true
      severity: warning

    identical_select_columns:
      enabled: true
      severity: info
```

Set `min_occurrences` higher (e.g., 5) to reduce noise in large projects where common CTE names like `final` or `base` are used by convention. Set it lower (e.g., 2) when enforcing strict re-use discipline.
Set `min_score` higher (e.g., `0.85`) when you only want near-duplicates, and lower (e.g., `0.65`) when you want broader consolidation suggestions during large legacy migrations. The Hub exposes this as three presets:

- **Conservative** — `min_score: 0.85`, `max_matches_per_model: 2`
- **Balanced** — `min_score: 0.72`, `max_matches_per_model: 3`
- **Discovery** — `min_score: 0.65`, `max_matches_per_model: 5`

Cluster recommendations use the same pairwise `min_score` threshold by default, so users only have to reason about one similarity threshold. The separate cluster knob is `min_cluster_size`, which defaults to `3`.

---

## Component Status

| Component | Purpose | Status |
|-----------|---------|--------|
| **CLI (`dbt-governance`)** | Scan, generate REVIEW.md/CLAUDE.md, validate config | ✅ Built |
| **Config schema** | Pydantic-validated YAML with 30+ rules across 9 categories | ✅ Built |
| **Discovery API client** | Fetch models, sources, tests, lineage from dbt Cloud GraphQL API | ✅ Built |
| **Rule engine** | 30+ deterministic rules across naming, structure, testing, documentation, materialization, style, governance, migration, re-use | ✅ Built |
| **REVIEW.md generator** | `dbt-governance generate review-md` | ✅ Built |
| **CLAUDE.md generator** | `dbt-governance generate claude-md` | ✅ Built |
| **SARIF output** | `--output sarif` for GitHub/GitLab/Azure DevOps code scanning | ✅ Built |
| **Central Governance UI** | Static Next.js configurator with live preview and download | ✅ Built (MVP) |
| **AI semantic reviewer — Anthropic** | Claude API integration for per-model semantic review | ✅ Built |
| **AI semantic reviewer — Google Gemini** | Gemini API integration (`gemini-2.5-pro`, `gemini-2.5-flash`) | ✅ Built |
| **AI semantic reviewer — OpenAI** | OpenAI API integration (`gpt-5.4`, `gpt-5-mini`) | ✅ Built |
| **GitHub PR annotations** | Post inline violations as GitHub Check run annotations on PR diffs | ✅ Built |
| **GitLab MR notes** | Post violations as GitLab discussion notes on MR diff lines | 🔲 Outstanding |
| **Changed-files mode** | `--changed-only`: git diff integration to scan only PR-modified files | ✅ Built |
| **Project file overlay** | Use checked-out SQL/YAML for PR-aware scans instead of only environment SQL | ✅ Built |
| **Fixture repo template** | Minimal dbt project + GitHub Actions workflow for end-to-end PR validation | ✅ Built |
| **Fixture PR validation harness** | Opens disposable good/bad PRs and writes markdown/json validation reports | ✅ Built |
| **Custom rule plugins** | Regex and yaml_key_exists custom rules from config | 🔲 Outstanding |
| **Pre-commit hook** | Fast rule subset runnable as a pre-commit hook | 🔲 Phase 4 |
| **Account-wide scanning** | Scan all projects in a dbt Cloud account in one run | 🔲 Phase 4 |

---

## Outstanding Work

### GitHub PR Annotations (`--github-annotate`)

This is now built. Violations are published as a GitHub Check run against the PR head SHA, and inline annotations appear on the changed files in the GitHub PR experience.

Built components:
- [x] `src/dbt_governance/output/github.py`
- [x] `--github-annotate` flag in `cli.py`
- [x] 50-annotation batching for large scans
- [x] README documentation for required workflow permissions and env vars

### GitLab MR Notes (`--gitlab-annotate`)

Posts violations as GitLab discussion threads pinned to specific diff lines in a Merge Request.

**What needs to be built:**
- [ ] `src/dbt_governance/output/gitlab.py` — GitLab REST API client using `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `CI_MERGE_REQUEST_IID` env vars
- [ ] Map violations to GitLab discussion note format with `position` (base SHA, head SHA, file path, line)
- [ ] `--gitlab-annotate` flag wired into `cli.py` scan command
- [ ] Graceful fallback: post as a single MR comment if line-level placement fails (e.g., file not in diff)
- [ ] Test against a real MR in a fixture GitLab project
- [ ] Document token scopes (`api` scope) in README and `.env.example`
- [ ] End-to-end test: verify notes appear on the correct diff lines

### PR Annotation Testing Plan

The GitHub path now has a concrete end-to-end workflow. The expected experience is:

1. CI checks out the PR branch
2. CI runs `dbt parse`
3. CI runs `dbt-governance scan --local --manifest target/manifest.json --project-dir . --changed-only --github-annotate`
4. Verify:
   - Annotations appear inline on the correct file and line in the PR diff.
   - The Check run status reflects the scan outcome (pass/fail).
   - The job exits with code 1 when `fail_on: error` and errors exist.
   - SARIF uploads separately for code scanning visibility, ideally as a non-blocking step when GitHub code scanning permissions are not guaranteed.
5. Test edge cases: zero violations, >50 violations (batching), binary/generated files skipped.

### Changed-Files Mode (`--changed-only`)

This is now built. The scanner computes changed files from git diff, still evaluates the full graph/context, and only reports findings for changed files or changed directories when the violation is directory-scoped.

Remaining work:
- [ ] Better base-branch detection across more CI providers
- [ ] Warning/telemetry when git diff fallback modes are used
- [ ] Additional tests for directory-level findings and non-standard repo layouts

### Fixture Repo Automation Harness

The fixture automation path is now built:

- `e2e/fixture_repo_template/`
- `scripts/e2e/bootstrap_fixture_repo.py`
- `scripts/e2e/run_fixture_pr_validation.py`

Expected experience:

1. Bootstrap a dedicated fixture repo from the template
2. Push it to GitHub and enable Actions
3. Run the validator to open a disposable good PR and bad PR
4. Review `artifacts/e2e/fixture-pr-validation.md` and `.json`

Remaining work:
- [ ] Add optional cleanup mode that closes generated PRs automatically
- [ ] Validate SARIF/code scanning alerts directly in the report, not only Check runs
- [ ] Add stronger assertion logic for Claude Code Review comments when that integration is installed
- [ ] Add support for provisioning a brand-new GitHub repo automatically instead of assuming an existing repo

### Custom Rule Plugins

The config schema supports `custom_rules` with `type: regex` and `type: yaml_key_exists`, but the scanner does not yet execute them.

**What needs to be built:**
- [ ] `src/dbt_governance/rules/custom.py` — `CustomRuleRunner` that iterates `config.custom_rules` and evaluates each against matching files
- [ ] `regex` type: compile the pattern, match against file content, emit violation per match with line number
- [ ] `yaml_key_exists` type: walk the parsed schema YAML for the key path, emit violation if absent
- [ ] Wire `CustomRuleRunner` into `scanner.py` so results appear in standard output alongside deterministic rules
- [ ] Test: fixture config with a regex rule detecting `ssn` columns, verify violation fires
- [ ] Test: fixture config with a `yaml_key_exists` rule checking for `meta.owner`, verify violation fires when missing

### AI Semantic Reviewer — Outstanding Items

The Anthropic, Gemini, and OpenAI review engines are implemented. Remaining work:

- [ ] `max_models_per_scan` enforcement — currently reviews all non-excluded models; need to add a cap and log a warning when truncated
- [ ] `cost_budget_per_scan_usd` enforcement — stop sending API requests when estimated cost exceeds the configured budget
- [ ] `confidence_threshold` filtering — Gemini and OpenAI responses do not yet include confidence; define a convention or strip low-confidence findings
- [ ] Tests for Gemini and OpenAI review paths (mock API responses)
- [ ] Terminal output: show token usage and estimated cost summary at the end of `--with-ai` scans

### Central Governance UI — Outstanding Items

MVP is running at `localhost:3002`. Remaining work:

- [ ] **Re-use rules tab** — the UI has tabs for naming/structure/testing/etc. but the reuse and migration categories are not yet surfaced as configurable panels
- [ ] **AI provider configuration panel** — UI needs provider toggles (Anthropic / OpenAI / Gemini), model dropdowns, and API key env var inputs
- [ ] **Live YAML preview** — verify that all rule changes immediately reflect in the YAML preview pane
- [ ] **Download all three files** — single "Download Package" button that downloads `.dbt-governance.yml`, `REVIEW.md`, and `CLAUDE.md` as a zip
- [ ] **dbt Cloud connection tester** — a "Test Connection" button in Settings that calls `dbt-governance cloud test-connection` against the configured credentials
