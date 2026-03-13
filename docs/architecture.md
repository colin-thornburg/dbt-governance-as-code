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

## Frontend Architecture: Central Governance UI

### Purpose
Give platform teams a **zero-YAML** way to define and tweak governance rules. Checkboxes, dropdowns, and simple inputs — no need to understand the config schema.

### Implementation
Static Next.js app (`guild-ui/`). No backend required — all config generation happens client-side. Platform team configures in browser, downloads three files, commits them to the dbt repo.

---

## End-to-End User Flow

### Flow 1: Set Up Standards (First Time)

```
1. Open the Central Governance UI (cd guild-ui && npm run dev)
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
   - dbt-governance scan --output sarif --output-file results.sarif
3. Upload SARIF for inline PR annotations
4. Commit REVIEW.md and CLAUDE.md — Claude Code Review discovers them automatically
5. Every PR now gets:
   - Deterministic scan (naming, structure, tests, docs, migration, re-use)
   - AI semantic review (business logic, descriptions, incremental patterns)
```

### Flow 3: Point at a Different Project

```bash
# Same config, different environment — pass via env vars or CLI flags
dbt-governance scan \
  --account-id 257364 \
  --environment-id 432623
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
| **AI semantic reviewer** | Claude/OpenAI API-powered per-model review | 🔲 Phase 2 |
