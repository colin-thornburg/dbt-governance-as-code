"""Tests for configuration parsing."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dbt_governance.config import (
    GovernanceConfig,
    Severity,
    generate_default_config,
    load_config,
)


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self):
        config = load_config(None)
        assert isinstance(config, GovernanceConfig)
        assert config.version == 1
        assert config.global_config.severity_default == Severity.WARNING

    def test_loads_from_yaml(self):
        yaml_content = """\
version: 1
project:
  name: "Test Project"
dbt_cloud:
  enabled: true
  account_id: 12345
  environment_id: 67890
global:
  fail_on: warning
naming:
  enabled: true
  rules:
    staging_prefix:
      enabled: true
      severity: error
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)

        assert config.project.name == "Test Project"
        assert config.dbt_cloud.enabled is True
        assert config.dbt_cloud.account_id == 12345
        assert config.dbt_cloud.environment_id == 67890
        assert config.global_config.fail_on == Severity.WARNING

    def test_raises_on_missing_file(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path.yml")


class TestGovernanceConfig:
    def test_is_rule_enabled(self):
        config = GovernanceConfig()
        assert config.is_rule_enabled("naming", "staging_prefix") is True

    def test_is_path_excluded(self):
        config = GovernanceConfig()
        assert config.is_path_excluded("dbt_packages/dbt_utils/models/foo.sql") is True
        assert config.is_path_excluded("models/staging/orders.sql") is False

    def test_get_rule_severity_falls_back(self):
        config = GovernanceConfig()
        severity = config.get_rule_severity("naming", "nonexistent_rule")
        assert severity == Severity.WARNING


class TestGenerateDefaultConfig:
    def test_generates_valid_yaml(self):
        content = generate_default_config()
        assert "version: 1" in content
        assert "dbt_cloud:" in content
        assert "naming:" in content
        assert "staging_prefix:" in content

    def test_round_trips(self):
        content = generate_default_config()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(content)
            f.flush()
            config = load_config(f.name)
        assert isinstance(config, GovernanceConfig)
        assert config.naming.enabled is True
