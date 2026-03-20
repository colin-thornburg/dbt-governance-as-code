# dbt Governance as Code

**Configurable governance enforcement for dbt Cloud projects — runs in CI on every PR, no warehouse required.**

Two core jobs:
1. **Detect** — Scan any dbt project and produce a prioritized report of violations, legacy migration debt, and re-use opportunities. Hand it to a team with specific, actionable fix instructions.
2. **Prevent** — Run 30+ deterministic rules on every pull request to block anti-patterns before they reach production.

---

## How it works

```
Central Governance UI          downloads 3 config files
(web configurator)        ──────────────────────────────▶   .dbt-governance.yml
                                                             REVIEW.md
                                                             CLAUDE.md
                                     │
                              git commit to repo
                                     │
                                     ▼
                            Your dbt repository
                           ┌─────────┴──────────┐
                     On every PR             On every PR
                           │                     │
                           ▼                     ▼
              ┌─────────────────────┐  ┌──────────────────────┐
              │  GitHub Actions /   │  │  Claude Code Review  │
              │  GitLab CI /        │  │                      │
              │  Azure Pipelines    │  │  Reads REVIEW.md     │
              │                     │  │  + CLAUDE.md auto-   │
              │  dbt-governance     │  │  matically on every  │
              │  scan               │  │  PR — no config      │
              │  30+ rules ~60s     │  │  needed once files   │
              │  SARIF annotations  │  │  are committed       │
              │  Fails CI           │  │  Inline PR comments  │
              └──────────┬──────────┘  └──────────────────────┘
                         │
              ┌──────────┴──────────┐
              │  dbt Cloud API  OR  │
              │  manifest.json      │
              │  (no warehouse)     │
              └─────────────────────┘
```

---

## Rule categories

| Category | What it checks |
|---|---|
| **Naming** | Staging prefix (`stg_`), intermediate (`int_`), marts (`fct_`, `dim_`) naming conventions |
| **Structure** | DAG layering — staging refs sources only, marts don't ref sources directly, no cross-layer skipping |
| **Testing** | Primary key tests, minimum test counts per model, source freshness, mart contracts |
| **Documentation** | Model and column descriptions, schema YAML presence, source documentation |
| **Materialization** | Staging should be views, incremental models must have `unique_key` and `on_schema_change` |
| **Style** | CTE patterns, no `SELECT *` in marts, final SELECT from named CTE, no hardcoded schemas |
| **Governance** | Meta-governance hygiene — config completeness, version pinning |
| **Migration** | Legacy ETL anti-patterns: hardcoded schemas, DDL statements, no `ref()`/`source()` calls, missing source definitions, no layer structure |
| **Re-use** | Duplicate source staging, shared CTE candidates, multiple models from the same source, identical SELECT column sets |

---

## Requirements

- **Python 3.11+**
- **dbt Cloud account** — for Cloud mode (recommended). Requires a service token with Metadata Only permissions.
- **Local `manifest.json`** — fallback for local scans without dbt Cloud. Generate with `dbt parse` (no warehouse needed).
- **Git provider** — GitHub, GitLab, or Azure DevOps for CI enforcement.
- **Anthropic API key** — optional, for Claude Code Review integration.

---

## Quick start

### Step 1 — Configure with the Central Governance UI

Open the [Central Governance UI](hub/) locally:

```bash
cd hub
npm install
npm run dev
# Opens at http://localhost:3000
```

Use the UI to configure your rule standards, then download three files:
- `.dbt-governance.yml` — the enforcement config
- `REVIEW.md` — review instructions for Claude Code Review
- `CLAUDE.md` — project context for Claude Code

### Step 2 — Commit the config files to your dbt repo

```bash
# In the root of your dbt project:
git add .dbt-governance.yml REVIEW.md CLAUDE.md
git commit -m "chore: add dbt governance config"
git push
```

> All three files must live in the **root directory** of your dbt repo. Claude Code reads `CLAUDE.md` from the root automatically.

### Step 3 — Install the CLI

```bash
pip install dbt-governance
```

### Step 4 — Set up your CI pipeline

Pick your git provider below. Then add the required environment variables as secrets (see [Secrets](#required-secrets)).

#### GitHub Actions

Create `.github/workflows/dbt-governance.yml`:

```yaml
name: dbt Governance
on:
  pull_request:
    branches: [main, develop]
    paths:
      - 'models/**'
      - '.dbt-governance.yml'
      - 'dbt_project.yml'
jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write   # required for SARIF upload
      pull-requests: write     # required for PR annotations
    steps:
      - uses: actions/checkout@v4
      - name: Install dbt-governance
        run: pip install dbt-governance
      - name: Run governance scan
        env:
          DBT_CLOUD_API_TOKEN: ${{ secrets.DBT_CLOUD_API_TOKEN }}
          DBT_CLOUD_ACCOUNT_ID: ${{ secrets.DBT_CLOUD_ACCOUNT_ID }}
          DBT_CLOUD_ENVIRONMENT_ID: ${{ secrets.DBT_CLOUD_ENVIRONMENT_ID }}
        run: |
          dbt-governance scan \
            --output sarif \
            --output-file governance.sarif
      - name: Upload SARIF to GitHub code scanning
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: governance.sarif
          category: dbt-governance
```

> **Note:** Inline PR annotations via SARIF require GitHub code scanning to be enabled. Go to **Settings → Code security and analysis → Code scanning → Enable**. For private repos this requires GitHub Advanced Security. Without it, violations still fail CI — they appear in the Actions log instead.

#### GitLab CI

Add to your `.gitlab-ci.yml`:

```yaml
dbt-governance:
  stage: lint
  image: python:3.11-slim
  script:
    - pip install dbt-governance
    - dbt-governance scan
  variables:
    DBT_CLOUD_API_TOKEN: $DBT_CLOUD_API_TOKEN
    DBT_CLOUD_ACCOUNT_ID: $DBT_CLOUD_ACCOUNT_ID
    DBT_CLOUD_ENVIRONMENT_ID: $DBT_CLOUD_ENVIRONMENT_ID
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

Add the three variables under **Settings → CI/CD → Variables**.

#### Azure DevOps / Azure Pipelines

Create `azure-pipelines.yml`:

```yaml
trigger: none
pr:
  branches:
    include: [main, develop]
  paths:
    include:
      - models/**
      - .dbt-governance.yml
      - dbt_project.yml

pool:
  vmImage: ubuntu-latest

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'
    displayName: Use Python 3.11

  - script: pip install dbt-governance
    displayName: Install dbt-governance

  - script: |
      dbt-governance scan \
        --output sarif \
        --output-file governance.sarif
    displayName: Run governance scan
    env:
      DBT_CLOUD_API_TOKEN: $(DBT_CLOUD_API_TOKEN)
      DBT_CLOUD_ACCOUNT_ID: $(DBT_CLOUD_ACCOUNT_ID)
      DBT_CLOUD_ENVIRONMENT_ID: $(DBT_CLOUD_ENVIRONMENT_ID)

  # With Azure DevOps Advanced Security — inline PR annotations
  - task: AdvancedSecurity-Publish@1
    inputs:
      SarifFile: governance.sarif
    displayName: Upload SARIF
    condition: always()

  # Without Advanced Security — publish as downloadable artifact
  # - task: PublishBuildArtifacts@1
  #   inputs:
  #     PathtoPublish: governance.sarif
  #     ArtifactName: governance-results
  #   condition: always()
```

Add the three variables under **Pipelines → Library → Variable Groups** (mark each as secret).

### Step 5 — Set up Claude Code Review (optional but recommended)

Once `CLAUDE.md` and `REVIEW.md` are committed, Claude Code Review works automatically for developers using Claude Code locally. For automated review on every PR, add a second GitHub Action:

```yaml
# .github/workflows/claude-review.yml
name: Claude Code Review
on:
  pull_request:
    paths: ['models/**', 'dbt_project.yml']
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: anthropics/claude-code-action@beta
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
```

Add `ANTHROPIC_API_KEY` to your GitHub repository secrets (from [console.anthropic.com](https://console.anthropic.com) → API keys).

---

## Required secrets

| Secret | Where to get it | Required for |
|---|---|---|
| `DBT_CLOUD_API_TOKEN` | dbt Cloud → Account Settings → Service Tokens → New Token (Metadata Only) | Cloud mode scan |
| `DBT_CLOUD_ACCOUNT_ID` | Visible in your dbt Cloud URL: `cloud.getdbt.com/accounts/12345` | Cloud mode scan |
| `DBT_CLOUD_ENVIRONMENT_ID` | dbt Cloud → Environments page | Cloud mode scan |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API keys | Claude Code Review (optional) |

For local development, create a `.env` file in the project root (never commit this):

```bash
# .env  (gitignored — see .env.example for the template)
DBT_CLOUD_API_TOKEN=dbtc_xxxxxxxxxxxxxxxxxxxx
DBT_CLOUD_ACCOUNT_ID=12345
DBT_CLOUD_ENVIRONMENT_ID=67890
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx  # optional
```

The CLI auto-loads `.env` via python-dotenv.

---

## CLI reference

```bash
# Initialize a default .dbt-governance.yml in the current directory
dbt-governance init

# Run a full scan (Cloud mode — reads from dbt Cloud Discovery API)
dbt-governance scan

# Run a scan and output SARIF for CI code scanning integrations
dbt-governance scan --output sarif --output-file results.sarif

# Run a scan using a local manifest.json (no dbt Cloud required)
dbt-governance scan --manifest-path target/manifest.json

# Scope scan to a single rule category
dbt-governance scan --category migration
dbt-governance scan --category reuse

# Generate the Claude Code Review files from your current config
dbt-governance generate review-md
dbt-governance generate claude-md

# Test your dbt Cloud connection
dbt-governance cloud test-connection

# List all available rules
dbt-governance rules

# Validate your .dbt-governance.yml
dbt-governance validate-config

# Print version
dbt-governance version
```

---

## Configuration reference

The full configuration lives in `.dbt-governance.yml`. Generate a default with `dbt-governance init`, or use the [Central Governance UI](hub/) for a visual editor.

```yaml
version: 1

project:
  name: "My dbt Project"
  description: "Governance baseline for all dbt Cloud projects."

dbt_cloud:
  enabled: true
  account_id: 12345        # DBT_CLOUD_ACCOUNT_ID env var also works
  environment_id: 67890   # DBT_CLOUD_ENVIRONMENT_ID env var also works

global:
  default_severity: error   # error | warning | info
  fail_on: error            # CI fails when any violation at this level or above is found
  exclude_paths:
    - "models/legacy/**"    # paths to skip entirely

# Each category has an enabled flag, severity override, and rule-specific options.
# See examples/.dbt-governance.yml for the complete reference.
naming:
  enabled: true
  rules:
    staging_prefix:
      enabled: true
      severity: error
    # ... more rules

ai_provider:
  provider: claude          # claude | openai | none
  model: claude-sonnet-4-6  # claude-sonnet-4-6 | claude-opus-4-6 | claude-haiku-4-5-20251001
  max_tokens_per_review: 4096
```

See [`examples/.dbt-governance.yml`](examples/.dbt-governance.yml) for a complete, annotated configuration.

---

## Local development

```bash
# Clone the repo
git clone https://github.com/your-org/dbt-governance.git
cd dbt-governance

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"

# Copy the environment template
cp .env.example .env
# Edit .env with your dbt Cloud credentials

# Run the test suite
pytest

# Run the linter
ruff check src/ tests/

# Run a scan against your own dbt project
dbt-governance scan
```

### Running the Central Governance UI locally

```bash
cd hub
npm install
npm run dev
# Opens at http://localhost:3000
```

The UI is a static Next.js app — no backend required. It generates config files for download; the actual scanning is done by the Python CLI.

---

## How this fits with the rest of the dbt ecosystem

These are all good tools. This project is designed to fill the gaps none of them cover — use them together.

| Tool | What it's great for | Why this fills a gap |
|---|---|---|
| **dbt_project_evaluator** (dbt Labs) | Deep DAG analysis using dbt models. Excellent for warehouse-backed periodic audits. | Requires a full `dbt run` against a warehouse — can't run pre-merge. Central Governance runs via the Discovery API in ~60s on every PR. |
| **SQLFluff** | SQL syntax and style linting. The gold standard for formatting consistency. | Purely syntactic — no knowledge of model layers, DAG structure, test coverage, or legacy migration patterns. Run both; they don't overlap. |
| **dbt Cloud recommendations** | Advisory guidance inside dbt Cloud Explorer — great for developer awareness. | Advisory only; can't fail CI, can't be versioned, can't be enforced consistently across all projects. Central Governance makes the same checks into enforceable policy. |
| **Great Expectations / Soda** | Runtime data quality validation — validates what's actually in your tables. | Tests data after loading, not code structure before merge. Entirely complementary layers — use both. |

---

## License

MIT — see [LICENSE](LICENSE).
