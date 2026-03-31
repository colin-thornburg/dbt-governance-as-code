# dbt Governance Fixture Repo

This repository is a dedicated end-to-end validation target for `dbt-governance`.

## What this repo validates

- Local PR scanning with `dbt parse`
- `--changed-only` filtering
- GitHub Check annotations via `--github-annotate`
- SARIF generation and upload
- Optional Claude Code Review comments if that integration is installed separately

## Expected behavior

- A harmless PR that only updates a config comment should pass
- A bad PR that adds a broken staging model should fail and produce annotations
- The validation harness will open disposable PRs against this repo and write a markdown/json report
