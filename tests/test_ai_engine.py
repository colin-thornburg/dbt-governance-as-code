"""Tests for provider-specific AI engine behavior."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from dbt_governance.ai.engine import AIReviewEngine, TokenUsage
from dbt_governance.config import GovernanceConfig


@pytest.mark.asyncio
async def test_openai_review_uses_max_completion_tokens(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"violations": []}'))],
            )

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, api_key: str):
            self.api_key = api_key
            self.chat = FakeChat()

    fake_openai = ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    config = GovernanceConfig.model_validate(
        {
            "ai_review": {
                "enabled": True,
                "provider": "openai",
                "model": "gpt-5-mini",
                "openai": {
                    "enabled": True,
                    "models": ["gpt-5-mini"],
                },
            }
        }
    )

    engine = AIReviewEngine(config)
    model = SimpleNamespace(
        name="stg_orders",
        layer="staging",
        materialization="view",
        file_path="models/staging/stg_orders.sql",
        description="Orders staging model",
        columns={},
        tests=[],
        raw_code="select 1 as order_id",
        compiled_code=None,
    )

    violations, usage = await engine._review_with_openai(
        models=[model],
        model_name="gpt-5-mini",
        api_key_env_var="OPENAI_API_KEY",
        usage=TokenUsage(provider="openai", model="gpt-5-mini"),
    )

    assert violations == []
    assert captured["model"] == "gpt-5-mini"
    assert captured["max_completion_tokens"] == config.ai_review.max_tokens_per_review
    assert "max_tokens" not in captured
    assert usage.models_reviewed == 1
