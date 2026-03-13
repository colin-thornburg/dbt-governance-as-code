"""Rich terminal output for governance scan results."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dbt_governance.config import Severity
from dbt_governance.scanner import ScanResult

console = Console()

SEVERITY_ICONS = {
    Severity.ERROR: "[bold red]ERROR[/bold red]",
    Severity.WARNING: "[bold yellow]WARNING[/bold yellow]",
    Severity.INFO: "[bold blue]INFO[/bold blue]",
}

SCORE_COLORS = {
    "excellent": "bold green",
    "good": "green",
    "needs_improvement": "yellow",
    "failing": "bold red",
}


def _score_label(score: float) -> tuple[str, str]:
    if score >= 90:
        return "Excellent", SCORE_COLORS["excellent"]
    elif score >= 75:
        return "Good", SCORE_COLORS["good"]
    elif score >= 60:
        return "Needs Improvement", SCORE_COLORS["needs_improvement"]
    else:
        return "Failing", SCORE_COLORS["failing"]


def _progress_bar(score: float, width: int = 12) -> str:
    filled = round(score / 100 * width)
    return "[green]" + "\u2588" * filled + "[/green][dim]" + "\u2591" * (width - filled) + "[/dim]"


def print_results(result: ScanResult) -> None:
    """Print formatted governance scan results to the terminal."""
    summary = result.summary
    mode = "[bold cyan]Cloud[/bold cyan]" if result.is_cloud_mode else "[dim]Local[/dim]"
    label, color = _score_label(summary.score)

    header = Table.grid(padding=(0, 2))
    header.add_column(justify="left")
    header.add_column(justify="right")
    header.add_row(
        f"[bold]Project:[/bold] {result.project_name}",
        f"[bold]Mode:[/bold] {mode}",
    )
    header.add_row(
        f"[bold]Models scanned:[/bold] {summary.models_scanned}",
        f"[bold]Rules evaluated:[/bold] {summary.rules_evaluated}",
    )
    header.add_row("", "")
    header.add_row(
        f"[bold red]Errors:[/bold red]   {summary.errors}",
        f"[bold yellow]Warnings:[/bold yellow] {summary.warnings}",
    )
    header.add_row(
        f"[bold blue]Info:[/bold blue]     {summary.info}",
        "",
    )

    console.print()
    console.print(Panel(header, title="[bold]dbt Governance Scan Results[/bold]", border_style="bright_blue"))

    if result.violations:
        console.print()
        for v in sorted(result.violations, key=lambda x: (x.severity.value, x.rule_id)):
            icon = SEVERITY_ICONS.get(v.severity, str(v.severity))
            console.print(f"  {icon} [dim]\\[{v.rule_id}][/dim] {v.file_path or v.model_name}")
            console.print(f"    {v.message}")
            if v.suggestion:
                console.print(f"    [dim]\u2192 {v.suggestion}[/dim]")
            console.print()

    console.print()
    score_table = Table(title="Category Breakdown", show_header=True, header_style="bold")
    score_table.add_column("Category", justify="left")
    score_table.add_column("Score", justify="right")
    score_table.add_column("", justify="left", width=14)
    score_table.add_column("Violations", justify="right")

    for cat in ["naming", "structure", "testing", "documentation", "materialization", "style"]:
        cs = summary.category_scores.get(cat)
        if cs:
            score_table.add_row(
                cat.capitalize(),
                f"{cs.score:.0f}%",
                _progress_bar(cs.score),
                str(cs.violations),
            )

    console.print(score_table)
    console.print()
    console.print(
        Panel(
            f"[{color}]Governance Score: {summary.score:.0f}/100 — {label}[/{color}]",
            border_style=color,
        )
    )
    console.print()
