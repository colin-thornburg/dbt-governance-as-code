"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from dbt_governance.config import GovernanceConfig, load_config
from dbt_governance.manifest import load_manifest
from dbt_governance.rules.base import RuleContext

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_manifest_path() -> Path:
    return FIXTURES_DIR / "sample_manifest.json"


@pytest.fixture
def sample_manifest(sample_manifest_path):
    return load_manifest(sample_manifest_path)


@pytest.fixture
def default_config() -> GovernanceConfig:
    return GovernanceConfig()


@pytest.fixture
def rule_context(sample_manifest, default_config) -> RuleContext:
    return RuleContext(
        manifest_data=sample_manifest,
        governance_config=default_config,
    )
