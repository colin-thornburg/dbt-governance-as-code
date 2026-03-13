"""Output formatters for governance scan results."""

from dbt_governance.output.json_report import to_json, write_json
from dbt_governance.output.sarif import to_sarif, write_sarif

__all__ = ["to_json", "to_sarif", "write_json", "write_sarif"]
