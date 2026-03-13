# Central Governance UI

Visual configurator for dbt governance standards. Configure rules with checkboxes and inputs, preview the generated config files, and download them ready to commit to any dbt repo.

## What it does

- Configure all governance rule categories (naming, structure, testing, documentation, materialization, style, migration, re-use) via a visual UI — no YAML editing required
- Preview `.dbt-governance.yml`, `REVIEW.md`, and `CLAUDE.md` live as you configure
- Download all three files with one click, ready to commit to your dbt repo
- Built-in "How it works" guide explaining the full architecture and CI setup

## Run locally

```bash
cd guild-ui
npm install
npm run dev
# Opens at http://localhost:3000
```

The app is fully static — no backend or database required. All config generation happens client-side.

## Build for deployment

```bash
npm run build
# Static output in .next/ — deploy to any static host (Vercel, Netlify, GitHub Pages, etc.)
```
