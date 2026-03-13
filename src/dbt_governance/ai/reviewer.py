"""Provider-aware AI review configuration helpers."""

from __future__ import annotations

import os

from pydantic import BaseModel

from dbt_governance.config import AIProvider, GovernanceConfig

DEFAULT_API_KEY_ENV_VARS = {
    AIProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    AIProvider.OPENAI: "OPENAI_API_KEY",
    AIProvider.GEMINI: "GEMINI_API_KEY",
}

SUPPORTED_MODELS = {
    AIProvider.ANTHROPIC: [
        "claude-sonnet-4-20250514",
        "claude-opus-4-1-20250805",
    ],
    AIProvider.OPENAI: [
        "gpt-5.4",
        "gpt-5-mini",
    ],
    AIProvider.GEMINI: [
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ],
}


class AIModelTarget(BaseModel):
    provider: AIProvider
    model: str
    api_key_env_var: str
    base_url: str | None = None


def get_supported_models() -> dict[str, list[str]]:
    """Return the curated list of supported frontier models by provider."""
    return {provider.value: list(models) for provider, models in SUPPORTED_MODELS.items()}


def resolve_provider_api_key_env_var(config: GovernanceConfig, provider: AIProvider) -> str:
    """Return the configured API key env var for a provider, or the default."""
    provider_config = config.ai_review.get_provider_config(provider)
    return provider_config.api_key_env_var or DEFAULT_API_KEY_ENV_VARS[provider]


def resolve_enabled_ai_models(config: GovernanceConfig) -> list[AIModelTarget]:
    """Resolve enabled provider/model targets from the governance config."""
    targets: list[AIModelTarget] = []
    if not config.ai_review.enabled:
        return targets

    for provider in config.ai_review.enabled_providers():
        provider_config = config.ai_review.get_provider_config(provider)
        for model in provider_config.models:
            targets.append(
                AIModelTarget(
                    provider=provider,
                    model=model,
                    api_key_env_var=resolve_provider_api_key_env_var(config, provider),
                    base_url=provider_config.base_url,
                )
            )
    return targets


def require_configured_api_keys(config: GovernanceConfig) -> dict[AIProvider, str]:
    """Return resolved API keys for enabled providers, or raise if missing."""
    keys: dict[AIProvider, str] = {}
    if not config.ai_review.enabled:
        return keys

    for provider in config.ai_review.enabled_providers():
        env_var = resolve_provider_api_key_env_var(config, provider)
        value = os.getenv(env_var)
        if not value:
            raise EnvironmentError(f"Missing API key for {provider.value}. Set {env_var}.")
        keys[provider] = value

    return keys
