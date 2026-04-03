"""AI-powered model reviewer with token usage tracking."""

from __future__ import annotations

import json
import os

from pydantic import BaseModel

from dbt_governance.cloud.models import ManifestData, ModelNode
from dbt_governance.config import AIProvider, GovernanceConfig, Severity
from dbt_governance.rules.base import Violation

# Per-million-token pricing: (input_usd, output_usd)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Claude 4 family
    "claude-opus-4-6": (15.0, 75.0),
    "claude-opus-4-1-20250805": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
    # OpenAI
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5.4": (5.0, 20.0),
    "gpt-5-mini": (0.30, 1.20),
    # Gemini
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.15, 0.60),
}


class TokenUsage(BaseModel):
    """Tracks LLM token consumption and estimated cost for an AI review run."""

    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    models_reviewed: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, input_tok: int, output_tok: int) -> None:
        self.input_tokens += input_tok
        self.output_tokens += output_tok
        self.models_reviewed += 1
        self._recalculate_cost()

    def _recalculate_cost(self) -> None:
        pricing = _MODEL_PRICING.get(self.model)
        if pricing:
            input_cost = (self.input_tokens / 1_000_000) * pricing[0]
            output_cost = (self.output_tokens / 1_000_000) * pricing[1]
            self.estimated_cost_usd = round(input_cost + output_cost, 6)


def _parse_violations(raw_text: str, model_name: str, file_path: str) -> list[Violation]:
    """Parse AI JSON response into Violation objects. Tolerant of markdown fencing."""
    text = raw_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    violations: list[Violation] = []
    for v in data.get("violations", []):
        sev_str = v.get("severity", "warning").lower()
        severity = {"error": Severity.ERROR, "warning": Severity.WARNING, "info": Severity.INFO}.get(
            sev_str, Severity.WARNING
        )
        violations.append(
            Violation(
                rule_id=v.get("rule_id", "ai.general"),
                severity=severity,
                model_name=model_name,
                file_path=file_path,
                message=v.get("message", ""),
                suggestion=v.get("suggestion"),
                ai_generated=True,
            )
        )
    return violations


class AIReviewEngine:
    """Orchestrates AI reviews across manifest models using the configured provider."""

    def __init__(self, config: GovernanceConfig):
        self.config = config

    async def review_all(
        self,
        manifest_data: ManifestData,
        changed_files: list[str] | None = None,
    ) -> tuple[list[Violation], TokenUsage]:
        """Review all non-excluded models. Returns violations and aggregate token usage."""
        from dbt_governance.ai.reviewer import require_configured_api_keys, resolve_enabled_ai_models

        if not self.config.ai_review.enabled:
            return [], TokenUsage()

        require_configured_api_keys(self.config)
        targets = resolve_enabled_ai_models(self.config)
        if not targets:
            return [], TokenUsage()

        # Use first enabled target
        target = targets[0]
        usage = TokenUsage(provider=target.provider.value, model=target.model)

        models_to_review = [
            m
            for m in manifest_data.models.values()
            if not self.config.is_path_excluded(m.file_path)
            and (m.raw_code or m.compiled_code)
            and (not changed_files or m.file_path in changed_files)
        ]

        if target.provider == AIProvider.ANTHROPIC:
            violations, usage = await self._review_with_anthropic(
                models_to_review, target.model, target.api_key_env_var, usage
            )
        elif target.provider == AIProvider.OPENAI:
            violations, usage = await self._review_with_openai(
                models_to_review, target.model, target.api_key_env_var, usage
            )
        elif target.provider == AIProvider.GEMINI:
            violations, usage = await self._review_with_gemini(
                models_to_review, target.model, target.api_key_env_var, usage
            )
        else:
            return [], usage

        return violations, usage

    async def _review_with_anthropic(
        self,
        models: list[ModelNode],
        model_name: str,
        api_key_env_var: str,
        usage: TokenUsage,
    ) -> tuple[list[Violation], TokenUsage]:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for AI review. "
                "Install it with: pip install 'dbt-governance[ai]'"
            )

        from dbt_governance.ai.prompts import build_review_prompt, build_system_prompt

        api_key = os.environ.get(api_key_env_var, "")
        client = anthropic.AsyncAnthropic(api_key=api_key)
        system_prompt = build_system_prompt(self.config.ai_review.additional_instructions)
        violations: list[Violation] = []

        for model in models:
            prompt = build_review_prompt(model)
            try:
                response = await client.messages.create(
                    model=model_name,
                    max_tokens=self.config.ai_review.max_tokens_per_review,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )
                usage.add(
                    input_tok=response.usage.input_tokens,
                    output_tok=response.usage.output_tokens,
                )
                raw_text = response.content[0].text if response.content else ""
                violations.extend(_parse_violations(raw_text, model.name, model.file_path))
            except Exception as exc:
                violations.append(
                    Violation(
                        rule_id="ai.review_error",
                        severity=Severity.INFO,
                        model_name=model.name,
                        file_path=model.file_path,
                        message=f"AI review skipped: {exc}",
                        ai_generated=True,
                    )
                )

        return violations, usage

    async def _review_with_openai(
        self,
        models: list[ModelNode],
        model_name: str,
        api_key_env_var: str,
        usage: TokenUsage,
    ) -> tuple[list[Violation], TokenUsage]:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for OpenAI AI review. "
                "Install it with: pip install 'dbt-governance[openai]'"
            )

        from dbt_governance.ai.prompts import build_review_prompt, build_system_prompt

        api_key = os.environ.get(api_key_env_var, "")
        client = AsyncOpenAI(api_key=api_key)
        system_prompt = build_system_prompt(self.config.ai_review.additional_instructions)
        violations: list[Violation] = []

        for model in models:
            prompt = build_review_prompt(model)
            try:
                response = await client.chat.completions.create(
                    model=model_name,
                    max_completion_tokens=self.config.ai_review.max_tokens_per_review,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                )
                if response.usage:
                    usage.add(
                        input_tok=response.usage.prompt_tokens,
                        output_tok=response.usage.completion_tokens,
                    )
                raw_text = response.choices[0].message.content or "" if response.choices else ""
                violations.extend(_parse_violations(raw_text, model.name, model.file_path))
            except Exception as exc:
                violations.append(
                    Violation(
                        rule_id="ai.review_error",
                        severity=Severity.INFO,
                        model_name=model.name,
                        file_path=model.file_path,
                        message=f"AI review skipped: {exc}",
                        ai_generated=True,
                    )
                )

        return violations, usage

    async def _review_with_gemini(
        self,
        models: list[ModelNode],
        model_name: str,
        api_key_env_var: str,
        usage: TokenUsage,
    ) -> tuple[list[Violation], TokenUsage]:
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            raise ImportError(
                "The 'google-genai' package is required for Gemini AI review. "
                "Install it with: pip install 'dbt-governance[gemini]'"
            )

        from dbt_governance.ai.prompts import build_review_prompt, build_system_prompt

        api_key = os.environ.get(api_key_env_var, "")
        client = genai.Client(api_key=api_key)
        system_prompt = build_system_prompt(self.config.ai_review.additional_instructions)
        violations: list[Violation] = []

        for model in models:
            prompt = build_review_prompt(model)
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        max_output_tokens=self.config.ai_review.max_tokens_per_review,
                    ),
                )
                if response.usage_metadata:
                    usage.add(
                        input_tok=response.usage_metadata.prompt_token_count or 0,
                        output_tok=response.usage_metadata.candidates_token_count or 0,
                    )
                raw_text = response.text or ""
                violations.extend(_parse_violations(raw_text, model.name, model.file_path))
            except Exception as exc:
                violations.append(
                    Violation(
                        rule_id="ai.review_error",
                        severity=Severity.INFO,
                        model_name=model.name,
                        file_path=model.file_path,
                        message=f"AI review skipped: {exc}",
                        ai_generated=True,
                    )
                )

        return violations, usage
