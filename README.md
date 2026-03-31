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

## What The Real Experience Is Like

After live testing, the cleanest operating model is:

- Use **cloud mode** for live sandbox and production validation.
- Use **local parse mode** for pull requests.

### Live account validation

Use cloud mode when you want to prove the app can connect to a real dbt Cloud account, fetch metadata, and produce a real governance report.

Typical commands:

```bash
dbt-governance cloud test-connection
dbt-governance scan --cloud
dbt-governance scan --cloud --with-ai
```

This is the right experience for:
- validating dbt Cloud credentials
- validating Discovery/Admin API access
- validating AI provider connectivity against a real environment

### Pull request validation

Use local mode in CI for PRs. The CI job should check out the branch, run `dbt parse`, and then scan the generated manifest with `--changed-only`.

Typical commands:

```bash
dbt parse
dbt-governance scan --local --manifest target/manifest.json --project-dir . --changed-only --github-annotate
```

This is the right experience for:
- catching new models added in a branch
- catching edits to unmerged SQL/YAML files
- producing GitHub Check annotations directly on the PR commit

### Recommended split

- **Cloud mode**: on-demand audits, sandbox validation, production posture checks
- **Local mode**: pre-merge CI, changed-files-only scans, fixture-repo PR automation

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

The reuse category now also includes model-level similarity scoring so the scanner can flag pairs of models that are structurally very similar even when they are not literal copy-pastes. It now also produces cluster-level recommendations, so the report can say "these 4 models should become one shared intermediate" instead of only showing disconnected pairs.
JSON scan output now also includes a dedicated `reuse_report` section with ranked actions, grouped into clusters first and strongest remaining pairs second, so governance teams can work from an explicit remediation queue.

---

## Requirements

- **Python 3.11+**
- **dbt Cloud account** — for Cloud mode (recommended). Requires a service token with Metadata Only permissions.
- **Local `manifest.json`** — fallback for local scans without dbt Cloud. Generate with `dbt parse` (no warehouse needed).
- **Git provider** — GitHub, GitLab, or Azure DevOps for CI enforcement.
- **AI provider API key** — optional, for semantic review. Supports Anthropic, OpenAI, and Gemini.

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

The Re-use tab includes dedicated similarity-scoring controls with conservative, balanced, and discovery presets so teams can rank consolidation opportunities without manually tuning thresholds first, then review both pairwise matches and multi-model cluster recommendations in plain English.
After running a scan in the UI, you can also download `REUSE_REPORT.md` to hand a ranked consolidation plan directly to a team.
That report now starts with an executive summary so governance leads can quickly understand overall re-use risk, how many high-priority items exist, and which consolidation opportunities should be staffed first.

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

To generate a ranked markdown handoff report for re-use remediation after a scan:

```bash
dbt-governance generate reuse-md --local --manifest target/manifest.json --project-dir .
```

### Step 4 — Set up your CI pipeline

Pick your git provider below. Then add the required environment variables as secrets (see [Secrets](#required-secrets)).

For PR validation, prefer **local parse mode** over cloud mode. It reflects the checked-out branch contents, including new models added in the PR. Keep cloud mode for live sandbox and production audits.

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
      - name: Install tooling
        run: pip install dbt-governance dbt-core dbt-duckdb
      - name: Write dbt profile for parse-only CI
        run: |
          mkdir -p "$RUNNER_TEMP/dbt"
          cat <<'EOF' > "$RUNNER_TEMP/dbt/profiles.yml"
          my_project:
            target: dev
            outputs:
              dev:
                type: duckdb
                path: ":memory:"
                threads: 1
          EOF
      - name: Parse dbt project
        run: dbt parse --profiles-dir "$RUNNER_TEMP/dbt"
      - name: Run governance scan
        env:
          GITHUB_TOKEN: ${{ github.token }}
          GITHUB_SHA: ${{ github.event.pull_request.head.sha }}
        run: |
          dbt-governance scan \
            --local \
            --manifest target/manifest.json \
            --project-dir . \
            --changed-only \
            --github-annotate \
            --output sarif \
            --output-file governance.sarif
      - name: Upload SARIF to GitHub code scanning
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        continue-on-error: true
        with:
          sarif_file: governance.sarif
          category: dbt-governance
```

> **Note:** `--github-annotate` publishes a GitHub Check run with inline annotations on the PR commit. SARIF upload is still recommended for code scanning visibility, but the Check run is the primary PR experience. In private repos or repos without compatible code scanning permissions enabled, keep the SARIF step as `continue-on-error: true` so governance enforcement still works even when code scanning upload is unavailable.

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

If Claude Code Review is installed on the repo, the user experience is:
- deterministic scanner failures in CI
- GitHub Check annotations on changed files
- optional Claude review comments for semantic feedback

---

## Required secrets

| Secret | Where to get it | Required for |
|---|---|---|
| `DBT_CLOUD_API_TOKEN` | dbt Cloud → Account Settings → Service Tokens → New Token (Metadata Only) | Cloud mode scan |
| `DBT_CLOUD_ACCOUNT_ID` | Visible in your dbt Cloud URL: `cloud.getdbt.com/accounts/12345` | Cloud mode scan |
| `DBT_CLOUD_ENVIRONMENT_ID` | dbt Cloud → Environments page | Cloud mode scan |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API keys | Anthropic semantic review or Claude Code Review (optional) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) → API keys | OpenAI semantic review (optional) |
| `GEMINI_API_KEY` | [ai.google.dev](https://ai.google.dev/) → API key | Gemini semantic review (optional) |

GitHub Actions automatically provides:
- `GITHUB_TOKEN`
- `GITHUB_SHA`
- `GITHUB_REPOSITORY`

For `pull_request` workflows, prefer overriding `GITHUB_SHA` with `${{ github.event.pull_request.head.sha }}` so the governance check attaches to the PR head commit instead of the temporary merge SHA. With that override in place, the default GitHub env plus `checks: write` is sufficient for `--github-annotate`.

For local development, create a `.env` file in the project root (never commit this):

```bash
# .env  (gitignored — see .env.example for the template)
DBT_CLOUD_API_TOKEN=dbtc_xxxxxxxxxxxxxxxxxxxx
DBT_CLOUD_ACCOUNT_ID=12345
DBT_CLOUD_ENVIRONMENT_ID=67890
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx  # optional
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxx    # optional
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxx            # optional
```

The CLI auto-loads `.env` via python-dotenv.

If you run `dbt-governance scan --with-ai` without explicitly enabling `ai_review` in the YAML,
the CLI will automatically pick the first available provider key in this order:
configured provider, OpenAI, Anthropic, Gemini.

---

## CLI reference

```bash
# Initialize a default .dbt-governance.yml in the current directory
dbt-governance init

# Run a live audit against the configured dbt Cloud environment
dbt-governance scan

# Force cloud mode explicitly
dbt-governance scan --cloud

# Run a PR-aware local scan after dbt parse
dbt-governance scan --local --manifest target/manifest.json --project-dir . --changed-only

# Publish GitHub Check annotations for the current commit
dbt-governance scan --local --manifest target/manifest.json --project-dir . --changed-only --github-annotate

# Run a scan and output SARIF for code scanning integrations
dbt-governance scan --output sarif --output-file results.sarif

# Run a scan using a local manifest.json
dbt-governance scan --local --manifest target/manifest.json

# Scope scan to specific rule categories
dbt-governance scan --rules migration,reuse

# Run semantic review using the first available AI provider key
dbt-governance scan --with-ai

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

---

## PR Automation Harness

This repo now includes a dedicated fixture-repo automation system under `scripts/e2e/`.

### What it does

- Bootstraps a compliant dbt fixture repository from `e2e/fixture_repo_template/`
- Runs PR validation in **local parse mode**
- Publishes GitHub Check annotations with `--github-annotate`
- Uploads SARIF for code scanning visibility
- Opens a disposable "good" PR and a disposable "bad" PR
- Collects check runs and PR comments into a markdown/json report

### Manual steps before it is real

1. Create a dedicated GitHub fixture repo.
2. Copy the template into that repo:

```bash
python scripts/e2e/bootstrap_fixture_repo.py /path/to/fixture-repo
```

3. Push the fixture repo to GitHub.
4. Enable GitHub Actions on that repo.
5. Optionally install Claude Code Review on that repo if you want semantic comments included in the observed experience.
6. Run the validator:

```bash
python scripts/e2e/run_fixture_pr_validation.py --repo your-org/your-fixture-repo
```

### Output

The harness writes:
- `artifacts/e2e/fixture-pr-validation.md`
- `artifacts/e2e/fixture-pr-validation.json`

Those artifacts tell you whether:
- the good PR passed
- the bad PR failed
- GitHub checks appeared
- review comments were observed

---

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
  severity_default: error   # error | warning | info
  fail_on: error            # CI fails when any violation at this level or above is found
  changed_files_only: true
  exclude_paths:
    - "target/"             # paths to skip entirely

# Each category has an enabled flag, severity override, and rule-specific options.
# See examples/.dbt-governance.yml for the complete reference.
naming:
  enabled: true
  rules:
    staging_prefix:
      enabled: true
      severity: error
    # ... more rules

ai_review:
  enabled: true
  provider: openai
  model: gpt-5-mini
  max_tokens_per_review: 4096
  openai:
    enabled: true
    api_key_env_var: OPENAI_API_KEY
    models:
      - gpt-5-mini
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
