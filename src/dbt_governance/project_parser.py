"""Parses dbt_project.yml and schema YAML files from disk."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_project_config(project_dir: Path | str = ".") -> dict:
    """Load dbt_project.yml from a directory."""
    path = Path(project_dir) / "dbt_project.yml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def discover_schema_files(project_dir: Path | str = ".") -> dict[str, dict]:
    """Find and parse all schema YAML files in the models directory."""
    project_dir = Path(project_dir)
    models_dir = project_dir / "models"
    schema_files: dict[str, dict] = {}

    if not models_dir.exists():
        return schema_files

    for yml_path in models_dir.rglob("*.yml"):
        rel_path = str(yml_path.relative_to(project_dir))
        with open(yml_path) as f:
            content = yaml.safe_load(f)
            if content:
                schema_files[rel_path] = content

    for yaml_path in models_dir.rglob("*.yaml"):
        rel_path = str(yaml_path.relative_to(project_dir))
        if rel_path not in schema_files:
            with open(yaml_path) as f:
                content = yaml.safe_load(f)
                if content:
                    schema_files[rel_path] = content

    return schema_files


def discover_sql_files(project_dir: Path | str = ".") -> dict[str, str]:
    """Find and read all SQL files in the models directory."""
    project_dir = Path(project_dir)
    models_dir = project_dir / "models"
    sql_files: dict[str, str] = {}

    if not models_dir.exists():
        return sql_files

    for sql_path in models_dir.rglob("*.sql"):
        rel_path = str(sql_path.relative_to(project_dir))
        sql_files[rel_path] = sql_path.read_text()

    return sql_files
