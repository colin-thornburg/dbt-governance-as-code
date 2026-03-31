# PR Automation Live Validation

This document records the live end-to-end validation of the PR automation layer for `dbt-governance`, including what was tested, what failed during early runs, what was fixed, and the final verified outcome.

## Scope

The goal of this testing pass was to validate the full pull-request experience for:

- `--changed-only`
- `--github-annotate`
- local manifest scanning with `dbt parse`
- GitHub Actions workflow behavior on good and bad PRs
- SARIF generation and upload behavior
- fixture-repo automation and reporting workflow

## Test Environment

- Main repo under test: `dbt-governance`
- Live fixture repo: [dbt-governance-fixture-live-20260314](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314)
- Fixture repo baseline branch: `main`
- Fixture workflow: `.github/workflows/dbt-governance.yml`
- Validation mode: GitHub Actions `pull_request` workflow using local manifest parsing

## What Was Tested

The live validation used a dedicated fixture dbt project with:

- a valid baseline project that should pass governance checks
- a "good" PR that only touched `.dbt-governance.yml` with a harmless comment
- a "bad" PR that added `models/staging/e2e_bad_orders.sql` with deliberate violations: bad staging naming, no tests, no description, no `ref()` / `source()`, and a hardcoded `prod.orders` reference

Each PR flow exercised:

1. GitHub checkout of the PR branch
2. `dbt parse`
3. `dbt-governance scan --local --manifest target/manifest.json --project-dir . --changed-only --github-annotate --output sarif --output-file governance.sarif`
4. GitHub Check publishing
5. SARIF upload attempt

## Iterations

### Iteration 1

PRs:

- Good: [#1](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/1)
- Bad: [#2](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/2)

Observed result:

- Both workflows failed.
- Root cause: the fixture workflow installed the previously published package, which did not yet contain the new `--project-dir`, `--changed-only`, and `--github-annotate` CLI behavior.

Fix applied:

- Added a fixture overlay mechanism so GitHub Actions clones the published repo source and then overlays the locally-developed runtime files before installation.

### Iteration 2

PRs:

- Good: [#3](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/3)
- Bad: [#4](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/4)

Observed result:

- Both workflows failed.
- `dbt parse` succeeded.
- `dbt-governance` ran and produced output.
- Root cause 1: `GITHUB_TOKEN` was not exported into the scan step, so `--github-annotate` could not publish a check run.
- Root cause 2: SARIF upload rejected the generated file because SARIF `fixes` entries were invalid without `artifactChanges`.

Fix applied:

- Exported `GITHUB_TOKEN` in the workflow scan step.
- Removed invalid SARIF `fixes` output and stored suggestions in SARIF `properties` instead.

### Iteration 3

PRs:

- Good: [#5](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/5)
- Bad: [#6](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/6)

Observed result:

- `dbt-governance` successfully wrote SARIF.
- `dbt-governance` successfully published a GitHub Check run from inside GitHub Actions.
- The workflow still failed overall because `github/codeql-action/upload-sarif@v3` returned `Resource not accessible by integration`.

Important finding:

- At this point the governance logic itself was working.
- The remaining failure was on the code-scanning upload integration, not on `dbt-governance` scanning or GitHub Check publishing.

Fix applied:

- Made the SARIF upload step non-blocking with `continue-on-error: true`.

### Iteration 4

PRs:

- Good: [#7](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/7)
- Bad: [#8](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/8)

Observed result:

- Good PR workflow finished `success`.
- Bad PR workflow finished `failure`.
- This was the first fully successful end-to-end validation cycle for overall workflow behavior.

Verified good PR behavior:

- Workflow check `scan` succeeded.
- Governance scan produced a clean result.
- Good PR URL: [#7](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/7)
- Governance summary: score `100.0`, `0` errors, `0` warnings, `0` info.

Verified bad PR behavior:

- Workflow check `scan` failed.
- Governance summary reported score `88.8`, `5` errors, `1` warning.
- Bad PR URL: [#8](https://github.com/colin-thornburg/dbt-governance-fixture-live-20260314/pull/8)
- Violations included `naming.staging_prefix`, `testing.primary_key_test_required`, `testing.minimum_test_coverage`, `documentation.model_description_required`, `migration.no_ref_or_source`, and `migration.hardcoded_environment_schema`.

## Final Live-Verified Outcome

The following behaviors were live-verified in GitHub Actions:

- `dbt parse` on the fixture repo
- local manifest scan with `--local --manifest target/manifest.json`
- changed-files filtering with `--changed-only`
- GitHub Check publishing with `--github-annotate`
- good PR passes
- bad PR fails
- bad PR receives governance findings in the published check output

## What The Governance Check Proved

The `dbt-governance` check run itself proved the intended behavior:

- clean PRs can produce a success result
- violating PRs can produce a failure result
- the bad PR summary included exactly the expected migration, naming, documentation, and testing findings

## Additional Hardening Applied After The Final Live Cycle

After the successful v4 cycle, one more workflow improvement was applied to the fixture baseline and template:

- override `GITHUB_SHA` in `pull_request` workflows to `${{ github.event.pull_request.head.sha }}`

Why:

- GitHub Actions uses a merge SHA by default on `pull_request` events
- binding `GITHUB_SHA` to the PR head SHA makes the governance check attach to the PR head commit rather than the temporary merge commit

This change was applied after the final live green/red validation cycle. The v4 cycle already proved the workflow behavior, and this follow-up makes the check placement more correct for long-term use.

## Files Changed During This Validation Effort

Inside `dbt-governance`, the testing and cleanup work added or updated:

- `src/dbt_governance/scanner.py`
- `src/dbt_governance/output/github.py`
- `src/dbt_governance/output/sarif.py`
- `src/dbt_governance/utils/diff.py`
- `src/dbt_governance/cli.py`
- `src/dbt_governance/ai/engine.py`
- `tests/test_scanner.py`
- `tests/test_github_output.py`
- `e2e/fixture_repo_template/`
- `scripts/e2e/bootstrap_fixture_repo.py`
- `scripts/e2e/run_fixture_pr_validation.py`
- `README.md`
- `docs/architecture.md`

## Remaining Caveats

- SARIF upload can still be unavailable in some repos depending on GitHub code scanning availability or integration permissions.
- The recommended workflow now treats SARIF upload as non-blocking so governance enforcement still works through the GitHub Check even when code scanning upload is unavailable.
- The fixture repo did not produce GitHub PR review comments through Claude Code Review because that integration was not installed as part of this test.

## Recommended Final Workflow Pattern

For GitHub PR validation, the recommended pattern is:

1. Run `dbt parse`
2. Run `dbt-governance scan --local --manifest target/manifest.json --project-dir . --changed-only --github-annotate`
3. Export `GITHUB_TOKEN`
4. Override `GITHUB_SHA` to `${{ github.event.pull_request.head.sha }}`
5. Upload SARIF as `continue-on-error: true`

## Bottom Line

The PR automation layer is now proven end to end for the GitHub Actions path:

- the scanner can evaluate only changed files
- the workflow can distinguish good vs bad PRs
- GitHub Check publishing works in live Actions
- governance failures surface on a real bad PR
- non-blocking SARIF upload keeps the good path green even when code scanning upload is restricted
