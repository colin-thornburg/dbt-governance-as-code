"""Prompt construction for AI-powered dbt model reviews."""

from __future__ import annotations

from dbt_governance.cloud.models import ModelNode

SYSTEM_PROMPT = """\
You are an expert dbt analytics engineer performing code review on dbt SQL models.
Your job is to identify governance violations — patterns that indicate poor practices,
maintenance risks, or architectural problems in dbt projects.

Respond ONLY with valid JSON in this exact format (no markdown, no prose):
{
  "violations": [
    {
      "rule_id": "<ai.rule_name>",
      "severity": "<error|warning|info>",
      "message": "<specific, actionable description of the problem>",
      "suggestion": "<concrete fix recommendation>"
    }
  ]
}

If no violations are found, return: {"violations": []}

Available rule IDs (use the best match, or ai.general for anything else):
- ai.business_logic_in_staging   — staging model applies business filters, joins, or aggregations
                                    that belong in an intermediate or mart model
- ai.complex_model_should_split  — model is doing too many things and should be broken into
                                    smaller intermediate steps for readability and testability
- ai.misleading_description      — the model or column description does not accurately reflect
                                    what the SQL actually computes
- ai.hardcoded_values            — magic numbers, hardcoded dates, status strings, or
                                    environment-specific schema names embedded in SQL
- ai.poor_cte_structure          — CTEs are poorly named (e.g. "cte1", "temp"), redundant,
                                    or structured in a way that hides logic
- ai.missing_column_context      — a column performs a complex calculation but has no description
                                    to explain its business meaning
- ai.general                     — any other significant quality or maintainability concern

Severity guide:
- error: blocks understanding or correctness (e.g. wrong description, severe anti-pattern)
- warning: significant smell that should be fixed (e.g. business logic in staging)
- info: low-priority improvement (e.g. rename a CTE for clarity)

Be specific: quote the actual SQL or column name in your message when relevant.
Only flag real issues — do not invent violations for well-written code.
"""


def build_system_prompt(additional_instructions: str = "") -> str:
    """Return the system prompt, optionally appending team-specific instructions."""
    if not additional_instructions or not additional_instructions.strip():
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + "\n\n## Additional team-specific rules\n" + additional_instructions.strip() + "\n"


def build_review_prompt(model: ModelNode) -> str:
    """Build a review prompt for a single model node."""
    parts = [
        f"## Model: {model.name}",
        f"Layer: {model.layer or 'unknown'}",
        f"Materialization: {model.materialization or 'unknown'}",
        f"File: {model.file_path}",
    ]

    parts.append(f"Description: {model.description or '(none)'}")

    column_descs = {
        name: col.description
        for name, col in model.columns.items()
        if col.description
    }
    if model.columns:
        col_names = list(model.columns.keys())
        parts.append(f"Columns ({len(col_names)}): {', '.join(col_names[:30])}")
    if column_descs:
        parts.append("Column descriptions:")
        for col, desc in list(column_descs.items())[:15]:
            parts.append(f"  - {col}: {desc}")

    if model.tests:
        test_names = [t.name for t in model.tests]
        parts.append(f"Tests: {', '.join(test_names[:10])}")

    sql = model.raw_code or model.compiled_code
    if sql:
        # Truncate very long SQL to stay within reasonable token limits
        if len(sql) > 6000:
            sql = sql[:6000] + "\n-- [truncated]"
        parts.append(f"\n## SQL\n```sql\n{sql}\n```")
    else:
        parts.append("\nSQL: (not available)")

    return "\n".join(parts)
