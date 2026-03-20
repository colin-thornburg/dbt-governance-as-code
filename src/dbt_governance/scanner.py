"""Scanner orchestrator — runs all enabled rules and collects results."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from dbt_governance.ai.engine import AIReviewEngine, TokenUsage
from dbt_governance.cloud.client import CloudHTTPClient
from dbt_governance.cloud.discovery import DiscoveryClient
from dbt_governance.cloud.models import ManifestData
from dbt_governance.config import GovernanceConfig, Severity, load_config
from dbt_governance.manifest import load_manifest
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, get_all_rules

import dbt_governance.rules.naming  # noqa: F401 — register rules
import dbt_governance.rules.structure  # noqa: F401
import dbt_governance.rules.testing  # noqa: F401
import dbt_governance.rules.documentation  # noqa: F401
import dbt_governance.rules.materialization  # noqa: F401
import dbt_governance.rules.style  # noqa: F401
import dbt_governance.rules.governance  # noqa: F401


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


class ScanResult(BaseModel):
    scan_id: str = ""
    timestamp: str = ""
    project_name: str = ""
    is_cloud_mode: bool = False
    summary: ScanSummary = Field(default_factory=ScanSummary)
    violations: list[Violation] = Field(default_factory=list)
    token_usage: TokenUsage | None = None


CATEGORY_WEIGHTS = {
    "naming": 0.15,
    "structure": 0.25,
    "testing": 0.25,
    "documentation": 0.15,
    "materialization": 0.10,
    "style": 0.10,
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


def run_scan(
    config_path: str | None = None,
    manifest_path: str | None = None,
    cloud_mode: bool | None = None,
    rule_categories: list[str] | None = None,
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
        sql_files: Pre-loaded SQL files (path -> content)
        schema_files: Pre-loaded schema YAML files (path -> parsed dict)
        project_config: Pre-loaded dbt_project.yml content
    """
    config = load_config(config_path)

    use_cloud = cloud_mode if cloud_mode is not None else config.dbt_cloud.enabled

    if use_cloud:
        manifest_data = asyncio.run(load_manifest_from_cloud(config))
        is_cloud = True
    else:
        mpath = manifest_path or "target/manifest.json"
        manifest_data = load_manifest(mpath)
        is_cloud = False

    context = RuleContext(
        manifest_data=manifest_data,
        project_config=project_config or {},
        schema_files=schema_files or {},
        sql_files=sql_files or {},
        governance_config=config,
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
        violations.extend(rule_violations)

    # AI semantic review (optional, runs after deterministic rules)
    token_usage: TokenUsage | None = None
    if with_ai or config.ai_review.enabled:
        engine = AIReviewEngine(config)
        ai_violations, token_usage = asyncio.run(engine.review_all(manifest_data))
        violations.extend(ai_violations)

    errors = sum(1 for v in violations if v.severity == Severity.ERROR)
    warnings = sum(1 for v in violations if v.severity == Severity.WARNING)
    infos = sum(1 for v in violations if v.severity == Severity.INFO)

    category_scores = _compute_category_scores(violations, manifest_data)
    overall_score = _compute_overall_score(category_scores)

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
