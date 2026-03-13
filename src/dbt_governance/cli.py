"""Typer CLI entrypoint for dbt-governance."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

# Load .env from cwd or parent dirs (e.g. when run from dbt project root)
load_dotenv()
from rich.console import Console

from dbt_governance import __version__
from dbt_governance.config import Severity, generate_default_config, load_config
from dbt_governance.generators import write_claude_md, write_review_md
from dbt_governance.output.json_report import write_json
from dbt_governance.output.sarif import to_sarif, write_sarif
from dbt_governance.output.terminal import print_results
from dbt_governance.rules.base import get_all_rules
from dbt_governance.scanner import run_scan

app = typer.Typer(
    name="dbt-governance",
    help="Configurable dbt best practices enforcement for dbt Cloud environments.",
    no_args_is_help=True,
)
console = Console()
generate_app = typer.Typer(help="Generate repository files from governance config.")
app.add_typer(generate_app, name="generate")


@app.command()
def scan(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to .dbt-governance.yml"),
    manifest: Optional[str] = typer.Option(None, "--manifest", "-m", help="Path to local manifest.json"),
    cloud: bool = typer.Option(False, "--cloud", help="Force dbt Cloud API mode"),
    local: bool = typer.Option(False, "--local", help="Force local manifest mode"),
    rules: Optional[str] = typer.Option(None, "--rules", "-r", help="Comma-separated rule categories to run"),
    with_ai: bool = typer.Option(False, "--with-ai", help="Enable AI semantic review"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output format: json, sarif"),
    output_file: Optional[str] = typer.Option(None, "--output-file", help="Write output to file"),
    fail_under: Optional[float] = typer.Option(None, "--fail-under", help="Fail if governance score is below this"),
):
    """Run a governance scan against a dbt project."""
    cloud_mode: bool | None = None
    if cloud:
        cloud_mode = True
    elif local:
        cloud_mode = False

    rule_categories = [r.strip() for r in rules.split(",")] if rules else None

    try:
        result = run_scan(
            config_path=config,
            manifest_path=manifest,
            cloud_mode=cloud_mode,
            rule_categories=rule_categories,
        )
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    except EnvironmentError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    if output == "json" or (output_file and output_file.endswith(".json")):
        if output_file:
            write_json(result, output_file)
            console.print(f"[green]JSON report written to {output_file}[/green]")
        else:
            console.print(result.model_dump_json(indent=2))
    elif output == "sarif" or (output_file and output_file.endswith(".sarif")):
        if output_file:
            write_sarif(result, output_file)
            console.print(f"[green]SARIF report written to {output_file}[/green]")
        else:
            console.print(to_sarif(result))
    else:
        print_results(result)

    if output_file and output == "json":
        pass

    gov_config = load_config(config)
    fail_severity = gov_config.global_config.fail_on

    has_failure = False
    if fail_severity == Severity.ERROR and result.summary.errors > 0:
        has_failure = True
    elif fail_severity == Severity.WARNING and (result.summary.errors > 0 or result.summary.warnings > 0):
        has_failure = True

    if fail_under is not None and result.summary.score < fail_under:
        console.print(
            f"[bold red]Governance score {result.summary.score:.0f} is below threshold {fail_under:.0f}[/bold red]"
        )
        has_failure = True

    if has_failure:
        raise typer.Exit(1)


@app.command()
def init(
    output: str = typer.Option(".dbt-governance.yml", "--output", "-o", help="Output file path"),
):
    """Initialize a new .dbt-governance.yml with sensible defaults."""
    path = Path(output)
    if path.exists():
        overwrite = typer.confirm(f"{path} already exists. Overwrite?")
        if not overwrite:
            raise typer.Abort()

    path.write_text(generate_default_config())
    console.print(f"[green]Created {path}[/green]")
    console.print("[dim]Edit this file to configure governance rules for your dbt project.[/dim]")


@app.command("validate-config")
def validate_config(
    config: str = typer.Option(".dbt-governance.yml", "--config", "-c", help="Path to config file"),
):
    """Validate a .dbt-governance.yml configuration file."""
    try:
        cfg = load_config(config)
        console.print(f"[green]Config is valid![/green]")
        console.print(f"  Project: {cfg.project.name}")
        console.print(f"  dbt Cloud: {'enabled' if cfg.dbt_cloud.enabled else 'disabled'}")
        enabled_categories = []
        for cat in ["naming", "structure", "testing", "documentation", "materialization", "style"]:
            cat_config = getattr(cfg, cat, None)
            if cat_config and cat_config.enabled:
                rule_count = len(cat_config.rules) if hasattr(cat_config, "rules") else 0
                enabled_categories.append(f"{cat} ({rule_count} rules)")
        console.print(f"  Enabled categories: {', '.join(enabled_categories)}")
        if cfg.ai_review.enabled:
            provider_summaries = []
            for provider in cfg.ai_review.enabled_providers():
                provider_cfg = cfg.ai_review.get_provider_config(provider)
                if provider_cfg.models:
                    provider_summaries.append(f"{provider.value}: {', '.join(provider_cfg.models)}")
            if provider_summaries:
                console.print(f"  AI providers: {'; '.join(provider_summaries)}")
    except Exception as e:
        console.print(f"[bold red]Invalid config:[/bold red] {e}")
        raise typer.Exit(1)


@app.command("rules")
def list_rules():
    """List all available governance rules."""
    import dbt_governance.rules.naming  # noqa: F401
    import dbt_governance.rules.structure  # noqa: F401
    import dbt_governance.rules.testing  # noqa: F401
    import dbt_governance.rules.documentation  # noqa: F401
    import dbt_governance.rules.materialization  # noqa: F401
    import dbt_governance.rules.style  # noqa: F401
    import dbt_governance.rules.governance  # noqa: F401

    from rich.table import Table

    all_rules = get_all_rules()

    table = Table(title="Available Governance Rules", show_header=True, header_style="bold")
    table.add_column("Rule ID", style="cyan")
    table.add_column("Category")
    table.add_column("Default Severity")
    table.add_column("Description")

    for rule_id in sorted(all_rules.keys()):
        rule_cls = all_rules[rule_id]
        severity_style = {
            Severity.ERROR: "bold red",
            Severity.WARNING: "yellow",
            Severity.INFO: "blue",
        }.get(rule_cls.default_severity, "")
        table.add_row(
            rule_id,
            rule_cls.category,
            f"[{severity_style}]{rule_cls.default_severity.value}[/{severity_style}]",
            rule_cls.description,
        )

    console.print(table)


@app.command("cloud")
def cloud_commands(
    action: str = typer.Argument(..., help="Action: test-connection"),
    config: str = typer.Option(".dbt-governance.yml", "--config", "-c"),
):
    """dbt Cloud API commands."""
    import asyncio

    if action == "test-connection":
        cfg = load_config(config)
        if not cfg.dbt_cloud.enabled:
            console.print("[yellow]dbt Cloud is not enabled in your config.[/yellow]")
            raise typer.Exit(1)

        from dbt_governance.cloud.admin import AdminClient
        from dbt_governance.cloud.client import CloudHTTPClient

        async def _test():
            http = CloudHTTPClient()
            try:
                admin = AdminClient(cfg.dbt_cloud.api_base_url, cfg.dbt_cloud.account_id, http)  # type: ignore
                ok = await admin.test_connection()
                return ok
            finally:
                await http.close()

        try:
            ok = asyncio.run(_test())
            if ok:
                console.print("[green]Successfully connected to dbt Cloud API![/green]")
            else:
                console.print("[red]Failed to connect to dbt Cloud API.[/red]")
                raise typer.Exit(1)
        except EnvironmentError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(1)
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)


@app.command()
def version():
    """Show the dbt-governance version."""
    console.print(f"dbt-governance {__version__}")


@generate_app.command("review-md")
def generate_review_md_command(
    config: str = typer.Option(".dbt-governance.yml", "--config", "-c", help="Path to config file"),
    output: str = typer.Option("REVIEW.md", "--output", "-o", help="Output file path"),
):
    """Generate REVIEW.md from governance config."""
    try:
        path = write_review_md(config_path=config, output_path=output)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]Created {path}[/green]")


@generate_app.command("claude-md")
def generate_claude_md_command(
    config: str = typer.Option(".dbt-governance.yml", "--config", "-c", help="Path to config file"),
    output: str = typer.Option("CLAUDE.md", "--output", "-o", help="Output file path"),
):
    """Generate CLAUDE.md from governance config."""
    try:
        path = write_claude_md(config_path=config, output_path=output)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]Created {path}[/green]")


def main():
    app()


if __name__ == "__main__":
    main()
