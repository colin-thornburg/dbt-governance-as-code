"""Scanner orchestrator — runs all enabled rules and collects results."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from dbt_governance.ai.engine import AIReviewEngine, TokenUsage
from dbt_governance.cloud.client import CloudHTTPClient
from dbt_governance.cloud.discovery import DiscoveryClient
from dbt_governance.cloud.models import ManifestData
from dbt_governance.config import AIProvider, GovernanceConfig, Severity, load_config
from dbt_governance.manifest import load_manifest
from dbt_governance.project_parser import discover_schema_files, discover_sql_files, load_project_config
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, get_all_rules
from dbt_governance.utils.diff import get_changed_files

import dbt_governance.rules.naming  # noqa: F401 — register rules
import dbt_governance.rules.structure  # noqa: F401
import dbt_governance.rules.testing  # noqa: F401
import dbt_governance.rules.documentation  # noqa: F401
import dbt_governance.rules.materialization  # noqa: F401
import dbt_governance.rules.style  # noqa: F401
import dbt_governance.rules.governance  # noqa: F401
import dbt_governance.rules.migration  # noqa: F401
import dbt_governance.rules.reuse  # noqa: F401
import dbt_governance.rules.security  # noqa: F401


class CategoryScore(BaseModel):
    category: str
    models_evaluated: int = 0
    models_passing: int = 0
    score: float = 100.0
    violations: int = 0


class ScanSummary(BaseModel):
    models_scanned: int = 0
    rules_evaluated: int = 0
    errors: int = 0
    warnings: int = 0
    info: int = 0
    score: float = 100.0
    category_scores: dict[str, CategoryScore] = Field(default_factory=dict)


class ReuseRecommendation(BaseModel):
    recommendation_type: str
    priority: str
    confidence_band: str = "low"
    summary: str
    suggested_shared_model: str | None = None
    model_names: list[str] = Field(default_factory=list)
    primary_model_name: str | None = None
    paired_model_name: str | None = None
    similarity_score: float | None = None
    cluster_average_score: float | None = None
    cluster_peak_score: float | None = None
    shared_inputs: list[str] = Field(default_factory=list)
    shared_selected_columns: list[str] = Field(default_factory=list)
    shared_aggregates: list[str] = Field(default_factory=list)
    shared_filters: list[str] = Field(default_factory=list)
    example_pairs: list[dict[str, str | float]] = Field(default_factory=list)


class ReuseReport(BaseModel):
    total_recommendations: int = 0
    cluster_count: int = 0
    remaining_pair_count: int = 0
    prioritized_actions: list[ReuseRecommendation] = Field(default_factory=list)
    clusters: list[ReuseRecommendation] = Field(default_factory=list)
    remaining_pairs: list[ReuseRecommendation] = Field(default_factory=list)


class ScanResult(BaseModel):
    scan_id: str = ""
    timestamp: str = ""
    project_name: str = ""
    is_cloud_mode: bool = False
    summary: ScanSummary = Field(default_factory=ScanSummary)
    violations: list[Violation] = Field(default_factory=list)
    reuse_report: ReuseReport | None = None
    token_usage: TokenUsage | None = None


CATEGORY_WEIGHTS = {
    "naming": 0.12,
    "structure": 0.20,
    "testing": 0.20,
    "documentation": 0.12,
    "materialization": 0.08,
    "style": 0.08,
    "migration": 0.12,
    "reuse": 0.08,
}

DEFAULT_AI_API_KEY_ENV_VARS = {
    AIProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    AIProvider.OPENAI: "OPENAI_API_KEY",
    AIProvider.GEMINI: "GEMINI_API_KEY",
}

DEFAULT_AI_MODELS = {
    AIProvider.ANTHROPIC: "claude-sonnet-4-20250514",
    AIProvider.OPENAI: "gpt-5.4",
    AIProvider.GEMINI: "gemini-2.5-pro",
}


async def load_manifest_from_cloud(config: GovernanceConfig) -> ManifestData:
    """Fetch manifest data from dbt Cloud Discovery API."""
    cloud_cfg = config.dbt_cloud
    http = CloudHTTPClient()
    try:
        discovery = DiscoveryClient(cloud_cfg.discovery_api_url, http)
        return await discovery.fetch_manifest_data(
            environment_id=cloud_cfg.environment_id,  # type: ignore[arg-type]
            account_id=cloud_cfg.account_id,  # type: ignore[arg-type]
        )
    finally:
        await http.close()


def _resolve_cli_ai_provider(config: GovernanceConfig) -> AIProvider:
    """Pick the first provider with a configured API key for ad-hoc CLI AI runs."""
    preferred_order = [config.ai_review.provider, AIProvider.OPENAI, AIProvider.ANTHROPIC, AIProvider.GEMINI]
    seen: set[AIProvider] = set()

    for provider in preferred_order:
        if provider in seen:
            continue
        seen.add(provider)
        provider_config = config.ai_review.get_provider_config(provider)
        env_var = provider_config.api_key_env_var or DEFAULT_AI_API_KEY_ENV_VARS[provider]
        if os.getenv(env_var):
            return provider

    return config.ai_review.provider


def _resolve_effective_config(config: GovernanceConfig, with_ai: bool) -> GovernanceConfig:
    """Apply CLI-driven overrides without mutating the persisted config on disk."""
    if not with_ai:
        return config

    ai_review = config.ai_review.model_copy(deep=True)
    ai_review.enabled = True

    provider = _resolve_cli_ai_provider(config)
    provider_config = ai_review.get_provider_config(provider).model_copy(deep=True)
    provider_config.enabled = True
    provider_config.api_key_env_var = provider_config.api_key_env_var or DEFAULT_AI_API_KEY_ENV_VARS[provider]
    if not provider_config.models:
        provider_config.models = [DEFAULT_AI_MODELS[provider]]

    setattr(ai_review, provider.value, provider_config)
    ai_review.provider = provider
    ai_review.model = provider_config.models[0]

    return config.model_copy(update={"ai_review": ai_review})


def _normalize_changed_paths(paths: list[str]) -> list[str]:
    return [Path(path).as_posix().lstrip("./") for path in paths]


def _violation_matches_changed_files(violation: Violation, changed_files: set[str]) -> bool:
    if not changed_files:
        return True

    violation_path = Path(violation.file_path).as_posix().lstrip("./")
    if not violation_path:
        return False

    if violation_path in changed_files:
        return True

    # Directory-level violations (for example, missing schema YAML in a model directory)
    # should surface when any changed file lives underneath that directory.
    prefix = violation_path.rstrip("/") + "/"
    return any(path.startswith(prefix) for path in changed_files)


def _load_project_files(
    project_dir: str | None,
    sql_files: dict[str, str] | None,
    schema_files: dict[str, dict] | None,
    project_config: dict | None,
) -> tuple[str, dict[str, str], dict[str, dict], dict]:
    resolved_project_dir = project_dir or os.getcwd()
    resolved_sql_files = sql_files if sql_files is not None else discover_sql_files(resolved_project_dir)
    resolved_schema_files = (
        schema_files if schema_files is not None else discover_schema_files(resolved_project_dir)
    )
    resolved_project_config = (
        project_config if project_config is not None else load_project_config(resolved_project_dir)
    )
    return resolved_project_dir, resolved_sql_files, resolved_schema_files, resolved_project_config


def _overlay_project_sql(manifest_data: ManifestData, sql_files: dict[str, str]) -> None:
    """Prefer checked-out project SQL over dbt Cloud/environment SQL for PR-aware scans."""
    if not sql_files:
        return

    for model in manifest_data.models.values():
        if model.file_path in sql_files:
            model.raw_code = sql_files[model.file_path]


def run_scan(
    config_path: str | None = None,
    manifest_path: str | None = None,
    cloud_mode: bool | None = None,
    rule_categories: list[str] | None = None,
    project_dir: str | None = None,
    changed_only: bool | None = None,
    sql_files: dict[str, str] | None = None,
    schema_files: dict[str, dict] | None = None,
    project_config: dict | None = None,
    with_ai: bool = False,
) -> ScanResult:
    """Run a governance scan and return results.

    Args:
        config_path: Path to .dbt-governance.yml
        manifest_path: Path to local manifest.json (local mode)
        cloud_mode: Force cloud or local mode. None = auto-detect from config.
        rule_categories: Only run rules from these categories
        project_dir: Root directory of the dbt project checkout
        changed_only: Restrict reported violations to changed files in the current git diff
        sql_files: Pre-loaded SQL files (path -> content)
        schema_files: Pre-loaded schema YAML files (path -> parsed dict)
        project_config: Pre-loaded dbt_project.yml content
    """
    config = _resolve_effective_config(load_config(config_path), with_ai)
    project_dir, resolved_sql_files, resolved_schema_files, resolved_project_config = _load_project_files(
        project_dir,
        sql_files,
        schema_files,
        project_config,
    )
    effective_changed_only = changed_only if changed_only is not None else config.global_config.changed_files_only

    use_cloud = cloud_mode if cloud_mode is not None else config.dbt_cloud.enabled

    if use_cloud:
        manifest_data = asyncio.run(load_manifest_from_cloud(config))
        is_cloud = True
    else:
        mpath = manifest_path or "target/manifest.json"
        manifest_data = load_manifest(mpath)
        is_cloud = False

    _overlay_project_sql(manifest_data, resolved_sql_files)

    changed_files: list[str] | None = None
    changed_file_set: set[str] = set()
    if effective_changed_only:
        changed_files = _normalize_changed_paths(get_changed_files(project_dir))
        changed_file_set = set(changed_files)

    context = RuleContext(
        manifest_data=manifest_data,
        project_config=resolved_project_config,
        schema_files=resolved_schema_files,
        sql_files=resolved_sql_files,
        governance_config=config,
        changed_files=changed_files,
        is_cloud_mode=is_cloud,
    )

    all_rules = get_all_rules()
    violations: list[Violation] = []
    rules_evaluated = 0

    for rule_id, rule_cls in all_rules.items():
        rule: BaseRule = rule_cls()

        if rule_categories and rule.category not in rule_categories:
            continue

        if not rule.is_enabled(config):
            continue

        rules_evaluated += 1
        rule_violations = rule.evaluate(context)
        if changed_file_set:
            rule_violations = [
                violation
                for violation in rule_violations
                if _violation_matches_changed_files(violation, changed_file_set)
            ]
        violations.extend(rule_violations)

    # AI semantic review (optional, runs after deterministic rules)
    token_usage: TokenUsage | None = None
    if with_ai or config.ai_review.enabled:
        engine = AIReviewEngine(config)
        ai_violations, token_usage = asyncio.run(engine.review_all(manifest_data, changed_files=changed_files))
        violations.extend(ai_violations)

    errors = sum(1 for v in violations if v.severity == Severity.ERROR)
    warnings = sum(1 for v in violations if v.severity == Severity.WARNING)
    infos = sum(1 for v in violations if v.severity == Severity.INFO)

    category_scores = _compute_category_scores(violations, manifest_data)
    overall_score = _compute_overall_score(category_scores)
    reuse_report = _build_reuse_report(violations)

    return ScanResult(
        scan_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        project_name=config.project.name,
        is_cloud_mode=is_cloud,
        summary=ScanSummary(
            models_scanned=len(manifest_data.models),
            rules_evaluated=rules_evaluated,
            errors=errors,
            warnings=warnings,
            info=infos,
            score=overall_score,
            category_scores=category_scores,
        ),
        violations=violations,
        reuse_report=reuse_report,
        token_usage=token_usage,
    )


def _compute_category_scores(
    violations: list[Violation], manifest_data: ManifestData
) -> dict[str, CategoryScore]:
    """Compute per-category governance scores."""
    total_models = len(manifest_data.models)
    if total_models == 0:
        return {}

    category_violations: dict[str, set[str]] = {}
    for v in violations:
        cat = v.rule_id.split(".")[0] if "." in v.rule_id else "other"
        category_violations.setdefault(cat, set()).add(v.model_name)

    scores = {}
    for cat in CATEGORY_WEIGHTS:
        failing_models = len(category_violations.get(cat, set()))
        passing = max(0, total_models - failing_models)
        score = (passing / total_models) * 100 if total_models > 0 else 100.0
        scores[cat] = CategoryScore(
            category=cat,
            models_evaluated=total_models,
            models_passing=passing,
            score=round(score, 1),
            violations=len([v for v in violations if v.rule_id.startswith(f"{cat}.")]),
        )

    return scores


def _compute_overall_score(category_scores: dict[str, CategoryScore]) -> float:
    """Compute weighted overall governance score."""
    if not category_scores:
        return 100.0

    weighted_sum = 0.0
    total_weight = 0.0
    for cat, weight in CATEGORY_WEIGHTS.items():
        if cat in category_scores:
            weighted_sum += category_scores[cat].score * weight
            total_weight += weight

    if total_weight == 0:
        return 100.0
    return round(weighted_sum / total_weight, 1)


def _recommendation_priority(
    recommendation_type: str,
    confidence_band: str,
    *,
    cluster_size: int | None = None,
    similarity_score: float | None = None,
    cluster_average_score: float | None = None,
) -> str:
    if recommendation_type == "cluster":
        if confidence_band == "high" or (cluster_size or 0) >= 4 or (cluster_average_score or 0.0) >= 0.82:
            return "high"
        if confidence_band == "medium":
            return "medium"
        return "low"

    if confidence_band == "high" and (similarity_score or 0.0) >= 0.88:
        return "high"
    if confidence_band in {"high", "medium"}:
        return "medium"
    return "low"


def _priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 3)


def _build_reuse_report(violations: list[Violation]) -> ReuseReport | None:
    clusters: list[ReuseRecommendation] = []
    cluster_model_sets: list[set[str]] = []

    for violation in violations:
        if violation.rule_id != "reuse.model_similarity_clusters":
            continue
        details = violation.details or {}
        cluster_models = list(details.get("cluster_models", []))
        confidence_band = str(details.get("confidence_band", "low"))
        recommendation = ReuseRecommendation(
            recommendation_type="cluster",
            priority=_recommendation_priority(
                "cluster",
                confidence_band,
                cluster_size=int(details.get("cluster_size", len(cluster_models) or 0)),
                cluster_average_score=float(details.get("cluster_average_score", 0.0) or 0.0),
            ),
            confidence_band=confidence_band,
            summary=violation.message,
            suggested_shared_model=details.get("suggested_shared_model"),
            model_names=cluster_models,
            primary_model_name=violation.model_name,
            cluster_average_score=details.get("cluster_average_score"),
            cluster_peak_score=details.get("cluster_peak_score"),
            shared_inputs=list(details.get("shared_inputs", [])),
            shared_selected_columns=list(details.get("shared_selected_columns", [])),
            shared_aggregates=list(details.get("shared_aggregates", [])),
            shared_filters=list(details.get("shared_filters", [])),
            example_pairs=list(details.get("cluster_example_pairs", [])),
        )
        clusters.append(recommendation)
        cluster_model_sets.append(set(cluster_models))

    remaining_pairs: list[ReuseRecommendation] = []
    for violation in violations:
        if violation.rule_id != "reuse.model_similarity_candidates":
            continue
        details = violation.details or {}
        pair_models = {violation.model_name, str(details.get("paired_model_name", ""))}
        if any(pair_models.issubset(cluster_set) for cluster_set in cluster_model_sets):
            continue

        confidence_band = str(details.get("confidence_band", "low"))
        remaining_pairs.append(
            ReuseRecommendation(
                recommendation_type="pair",
                priority=_recommendation_priority(
                    "pair",
                    confidence_band,
                    similarity_score=float(details.get("similarity_score", 0.0) or 0.0),
                ),
                confidence_band=confidence_band,
                summary=violation.message,
                suggested_shared_model=details.get("suggested_shared_model"),
                model_names=[violation.model_name, str(details.get("paired_model_name", ""))],
                primary_model_name=violation.model_name,
                paired_model_name=details.get("paired_model_name"),
                similarity_score=details.get("similarity_score"),
                shared_inputs=list(details.get("shared_inputs", [])),
                shared_selected_columns=list(details.get("shared_selected_columns", [])),
                shared_aggregates=list(details.get("shared_aggregates", [])),
                shared_filters=list(details.get("shared_filters", [])),
            )
        )

    def sort_key(recommendation: ReuseRecommendation) -> tuple:
        score = (
            recommendation.cluster_average_score
            if recommendation.recommendation_type == "cluster"
            else recommendation.similarity_score
        ) or 0.0
        return (_priority_rank(recommendation.priority), -score, -len(recommendation.model_names), recommendation.summary)

    clusters.sort(key=sort_key)
    remaining_pairs.sort(key=sort_key)
    prioritized_actions = [*clusters, *remaining_pairs]

    if not prioritized_actions:
        return None

    return ReuseReport(
        total_recommendations=len(prioritized_actions),
        cluster_count=len(clusters),
        remaining_pair_count=len(remaining_pairs),
        prioritized_actions=prioritized_actions,
        clusters=clusters,
        remaining_pairs=remaining_pairs,
    )
