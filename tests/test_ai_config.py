"""Tests for AI provider configuration support."""

from __future__ import annotations

import pytest

from dbt_governance.ai.reviewer import (
    get_supported_models,
    require_configured_api_keys,
    resolve_enabled_ai_models,
    resolve_provider_api_key_env_var,
)
from dbt_governance.config import AIProvider, GovernanceConfig


def test_ai_review_legacy_model_populates_anthropic_provider():
    config = GovernanceConfig.model_validate(
        {
            "ai_review": {
                "enabled": True,
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
            }
        }
    )

    assert config.ai_review.anthropic.models[0] == "claude-sonnet-4-20250514"


def test_ai_review_supports_multiple_providers_and_models():
    config = GovernanceConfig.model_validate(
        {
            "ai_review": {
                "enabled": True,
                "provider": "openai",
                "model": "gpt-5.4",
                "openai": {
                    "enabled": True,
                    "models": ["gpt-5.4", "gpt-5-mini"],
                },
                "gemini": {
                    "enabled": True,
                    "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
                },
            }
        }
    )

    targets = resolve_enabled_ai_models(config)

    assert ("openai", "gpt-5.4") in [(target.provider.value, target.model) for target in targets]
    assert ("openai", "gpt-5-mini") in [(target.provider.value, target.model) for target in targets]
    assert ("gemini", "gemini-2.5-pro") in [(target.provider.value, target.model) for target in targets]


def test_ai_review_resolves_default_env_vars():
    config = GovernanceConfig.model_validate(
        {
            "ai_review": {
                "enabled": True,
                "openai": {"enabled": True, "models": ["gpt-5.4"]},
                "gemini": {"enabled": True, "models": ["gemini-2.5-pro"]},
            }
        }
    )

    assert resolve_provider_api_key_env_var(config, AIProvider.OPENAI) == "OPENAI_API_KEY"
    assert resolve_provider_api_key_env_var(config, AIProvider.GEMINI) == "GEMINI_API_KEY"


def test_ai_review_requires_configured_api_keys(monkeypatch: pytest.MonkeyPatch):
    config = GovernanceConfig.model_validate(
        {
            "ai_review": {
                "enabled": True,
                "openai": {"enabled": True, "models": ["gpt-5.4"]},
            }
        }
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    resolved = require_configured_api_keys(config)

    assert resolved[AIProvider.OPENAI] == "test-openai-key"


def test_ai_review_raises_for_missing_api_key(monkeypatch: pytest.MonkeyPatch):
    config = GovernanceConfig.model_validate(
        {
            "ai_review": {
                "enabled": True,
                "gemini": {"enabled": True, "models": ["gemini-2.5-pro"]},
            }
        }
    )

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(EnvironmentError):
        require_configured_api_keys(config)


def test_supported_models_expose_openai_and_gemini():
    supported = get_supported_models()

    assert "openai" in supported
    assert "gemini" in supported
    assert supported["openai"] == ["gpt-5.4", "gpt-5-mini"]
    assert "gemini-2.5-pro" in supported["gemini"]
    # Gemini 3 models per https://ai.google.dev/gemini-api/docs/gemini-3
    assert "gemini-3.1-pro-preview" in supported["gemini"]
    assert "gemini-3-flash-preview" in supported["gemini"]
