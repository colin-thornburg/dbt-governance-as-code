# dbt governance for your team (simple setup)

This guide explains **exactly what to do** so you can enforce dbt standards **without** needing heavy security approval up front. If you already use **Microsoft Copilot Code Review** and **Gemini** (and may add **Claude** later), you can start with those tools first; the deterministic scanner can come later.

---

## What you are doing (one sentence)

You commit a **small config file** (`.dbt-governance.yml`) and **auto-generated review instructions** (`REVIEW.md` and optionally `CLAUDE.md`) into your dbt repo. Your existing **Copilot Code Review** and **Gemini** read those files and check every pull request against **your** rules—same standards for everyone, no new mystery service required to get started.

---

## Why this is the practical path

| Approach | What it is | When to use it |
|----------|------------|----------------|
| **A. Review docs in the repo (start here)** | Rules live in markdown that Copilot and Gemini are instructed to follow | **Right now** — fastest, uses tools you already approved |
| **B. Local scanner (optional, later)** | The `dbt-governance` CLI reads your project + `manifest.json` and reports violations | When you want **automated** checks in CI with clear pass/fail |
| **C. dbt Cloud APIs (optional, later)** | Richer metadata from dbt Cloud | When security is comfortable with **metadata-only** API access |

**You do not need a dbt package** for this workflow. Governance rules are **project configuration + review instructions**, not dbt SQL macros. A dbt package is the wrong shape unless you rebuild everything in SQL inside dbt (a different kind of tool).

---

## Step 1 — Add the governance config to the repo

1. In the **root of your dbt project** (same level as `dbt_project.yml`), add:

   - **`.dbt-governance.yml`**  
     This file lists **which rules are on**, how strict they are (error vs warning), and any patterns (e.g. naming).

2. You can scaffold a starter file with:

   ```bash
   dbt-governance init
   ```

3. Treat it like any other **team standard** file: **review it in a PR** and keep it **version-controlled**.

**What the team needs to know:** editing this file is how your platform team or lead engineer **changes the rules**. Everyone sees the same file in Git.

---

## Step 2 — Generate review instructions from the config

From the directory that contains `.dbt-governance.yml`, run:

```bash
dbt-governance generate review-md
dbt-governance generate claude-md
```

That produces:

- **`REVIEW.md`** — checklist-style rules for PR reviewers, Copilot, and Gemini.
- **`CLAUDE.md`** — project context for **Claude Code** (or any assistant that reads repo context files).

**Commit `REVIEW.md` and `CLAUDE.md` to the repo** (or commit `REVIEW.md` only if you are not using Claude yet).

**Why:** Copilot Code Review and Gemini work best when the rules are **in the repository**, not only in chat or a ticket.

---

## Step 3 — Make sure Microsoft Copilot Code Review sees the rules

**Goal:** Every pull request that touches `models/`, `macros/`, or YAML gets reviewed against `REVIEW.md`.

**Practical actions:**

1. Keep **`REVIEW.md` at the repo root** (or one documented path—be consistent).
2. In your **GitHub / Azure DevOps** settings, use your org’s pattern for **custom instructions** or **repository instructions**, and point them at `REVIEW.md` or add a line such as: *Apply governance rules in `REVIEW.md`.*
3. Add a short note in **`README.md`**: *PR reviewers and Copilot should follow `REVIEW.md`.*

**Simple rule for the team:** If you change `.dbt-governance.yml`, you **regenerate and commit** `REVIEW.md` in the **same PR** so Copilot and humans stay in sync.

---

## Step 4 — Use Gemini the same way

Use Gemini **with repo context**:

1. **Attach or paste** `REVIEW.md` (or the PR diff) and ask: *Check this PR against `REVIEW.md`.*
2. Ask **concrete** questions: *List any violations of staging naming in this diff.*

**Tip:** The more your rules live in **one file** (`REVIEW.md`), the easier Gemini is to use consistently.

---

## Step 5 — When you add Claude (or Claude Code)

When Claude is approved:

1. Keep **`CLAUDE.md`** in the repo (regenerated from the same `.dbt-governance.yml`).
2. Many Claude setups **auto-read `CLAUDE.md`** in the project root.

**Reminder:** `REVIEW.md` = *what to check*; `CLAUDE.md` = *how the project is structured*. Regenerate both when the YAML changes.

---

## Step 6 — Optional: turn on the automated scanner (later)

When security is ready:

1. Run **`dbt parse`** in CI to produce **`target/manifest.json`** (no warehouse needed for parse in typical setups).
2. Install the CLI (for example `pip install dbt-governance`) and run a **local** scan:

   ```bash
   dbt-governance scan --local --manifest target/manifest.json --config .dbt-governance.yml
   ```

3. Optionally output **SARIF** or **JSON** for your existing code-scanning or PR checks:

   ```bash
   dbt-governance scan --local --manifest target/manifest.json --output sarif --output-file results.sarif
   ```

**Narrative for security:** *Reads Git + manifest JSON; does not connect to the data warehouse unless you configure optional Cloud mode.*

---

## What to do when rules change (checklist)

- [ ] Edit **`.dbt-governance.yml`**
- [ ] Run **`dbt-governance generate review-md`** (and **`generate claude-md`** if you use it)
- [ ] Commit the updated **`REVIEW.md`** / **`CLAUDE.md`** in the **same PR**
- [ ] Mention in the PR: *Governance rules updated—follow `REVIEW.md`*

---

## FAQ (plain language)

**Do we need to install new software on day one?**  
No. Start with **committed YAML + `REVIEW.md`** and your existing **Copilot** and **Gemini**. Install `dbt-governance` only when you want the CLI or CI scanner.

**Is this as strong as automated CI gates?**  
Not exactly—Copilot and Gemini follow instructions, but **CI with `dbt-governance scan`** gives a hard pass/fail. Use **Phase A** first, **Phase B** when ready.

**Who “executes” the YAML?**  
Your **CI job or a developer** runs `generate review-md` / `generate claude-md` after YAML changes. You do **not** need an external vendor running commands on your behalf for the review-doc approach.

**Why not a dbt package?**  
This governance tool is **not** a bundle of dbt models; it is **config + review text + optional Python scanner**. A dbt package does not replace that without rebuilding the rules in SQL.

---

## Summary

1. Add **`.dbt-governance.yml`** (use `dbt-governance init` if helpful).
2. Run **`dbt-governance generate review-md`** and **`generate claude-md`**, then commit **`REVIEW.md`** / **`CLAUDE.md`**.
3. Point **Copilot Code Review** at **`REVIEW.md`** (per your org’s settings).
4. Use **Gemini** with **`REVIEW.md`** as the checklist.
5. Use **`CLAUDE.md`** when you adopt **Claude** or **Claude Code**.
6. Add **`dbt-governance scan --local`** in CI when security approves it.

That is the **simplest path** that still matches how most teams already review code.
