"""Re-use and redundancy detection rules.

These rules surface opportunities to consolidate duplicated logic across models —
a critical problem in legacy ETL migrations where each pipeline was independent
and dbt's shared-model capabilities were never leveraged.

The goal is not to flag every similarity, but to find the high-confidence cases
where two or more models are clearly doing the same work and should share a
common upstream model instead.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from math import ceil
from typing import Iterable

import sqlglot
from sqlglot import exp

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule


_REF_PATTERN = re.compile(r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", re.IGNORECASE)
_SOURCE_PATTERN = re.compile(
    r"\{\{\s*source\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}",
    re.IGNORECASE,
)
@dataclass(slots=True)
class ModelSimilarityProfile:
    model_name: str
    file_path: str
    layer: str
    inputs: frozenset[str]
    selected_columns: frozenset[str]
    join_targets: frozenset[str]
    filter_columns: frozenset[str]
    group_by_columns: frozenset[str]
    aggregate_functions: frozenset[str]
    cte_names: frozenset[str]


@dataclass(slots=True)
class SimilarityEdge:
    left: ModelSimilarityProfile
    right: ModelSimilarityProfile
    score: float
    input_score: float
    selected_score: float
    join_score: float
    filter_score: float
    group_score: float
    agg_score: float
    cte_score: float


def _sanitize_sql_for_similarity(sql: str) -> str:
    sql = _REF_PATTERN.sub(lambda m: f"ref_{m.group(1).replace('.', '_')}", sql)
    sql = _SOURCE_PATTERN.sub(
        lambda m: f"source_{m.group(1).replace('.', '_')}_{m.group(2).replace('.', '_')}",
        sql,
    )
    return sql


def _expr_name(node: exp.Expression | str | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, str):
        return node.lower()
    if isinstance(node, exp.Table):
        table_name = node.name
        return table_name.lower() if table_name else None
    alias_or_name = getattr(node, "alias_or_name", None)
    if alias_or_name:
        return alias_or_name.lower()
    if isinstance(node, exp.Column):
        return node.name.lower()
    if isinstance(node, exp.Identifier):
        return node.name.lower()
    return node.sql(dialect="duckdb").lower()


def _normalized_select_name(node: exp.Expression) -> str | None:
    if isinstance(node, exp.Alias):
        alias_name = _expr_name(node)
        if alias_name:
            return alias_name
        node = node.this
    return _expr_name(node)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _normalized_sql_fragment(sql: str, *, strip_qualifiers: bool = False) -> str:
    normalized = re.sub(r"\s+", " ", sql.strip()).lower()
    return normalized


def _normalized_expression_sql(node: exp.Expression, *, strip_qualifiers: bool = False) -> str:
    expression = node.copy()

    def _normalize(current: exp.Expression) -> exp.Expression:
        if isinstance(current, exp.Table):
            current.set("alias", None)
            return current
        if strip_qualifiers and isinstance(current, exp.Column):
            return exp.column(current.name)
        return current

    expression = expression.transform(_normalize)
    return _normalized_sql_fragment(
        expression.sql(dialect="duckdb", pretty=False, normalize=True),
    )


def _root_select(parsed: exp.Expression) -> exp.Select | None:
    if isinstance(parsed, exp.Select):
        return parsed
    return parsed.find(exp.Select)


def _projection_expression(node: exp.Expression) -> exp.Expression:
    return node.this if isinstance(node, exp.Alias) else node


def _is_trivial_passthrough_select(select: exp.Select) -> bool:
    if select.args.get("where") or select.args.get("group") or select.args.get("having"):
        return False
    if list(select.find_all(exp.Join)):
        return False

    projections = select.expressions or []
    if not projections:
        return False
    return all(isinstance(_projection_expression(projection), exp.Column) for projection in projections)


def _parse_similarity_profile(model_name: str, file_path: str, layer: str, sql: str) -> ModelSimilarityProfile | None:
    try:
        parsed = sqlglot.parse_one(_sanitize_sql_for_similarity(sql), read="duckdb")
    except sqlglot.errors.ParseError:
        return None

    inputs: set[str] = set()
    join_targets: set[str] = set()
    selected_columns: set[str] = set()
    filter_columns: set[str] = set()
    group_by_columns: set[str] = set()
    aggregate_functions: set[str] = set()
    cte_names: set[str] = set()

    for cte in parsed.find_all(exp.CTE):
        cte_name = _expr_name(cte.alias)
        if cte_name:
            cte_names.add(cte_name)

    for table in parsed.find_all(exp.Table):
        table_name = _expr_name(table)
        if table_name:
            inputs.add(table_name)

    for join in parsed.find_all(exp.Join):
        target = join.this
        if isinstance(target, exp.Table):
            table_name = _expr_name(target)
            if table_name:
                join_targets.add(table_name)

    select = _root_select(parsed)
    if select is not None:
        for projection in select.expressions:
            normalized = _normalized_select_name(projection)
            if normalized:
                selected_columns.add(normalized)

    for where in parsed.find_all(exp.Where):
        for column in where.find_all(exp.Column):
            column_name = _expr_name(column)
            if column_name:
                filter_columns.add(column_name)

    for group in parsed.find_all(exp.Group):
        for expression in group.expressions:
            group_name = _expr_name(expression)
            if group_name:
                group_by_columns.add(group_name)

    for func in parsed.find_all(exp.AggFunc):
        aggregate_functions.add(func.key.lower())

    # CTE naming varies wildly across teams and migrations. For similarity scoring,
    # external lineage matters more than whether two developers called a CTE "base"
    # or "orders_base", so remove local CTE references from the input/join signals.
    inputs.difference_update(cte_names)
    join_targets.difference_update(cte_names)

    return ModelSimilarityProfile(
        model_name=model_name,
        file_path=file_path,
        layer=layer,
        inputs=frozenset(inputs),
        selected_columns=frozenset(selected_columns),
        join_targets=frozenset(join_targets),
        filter_columns=frozenset(filter_columns),
        group_by_columns=frozenset(group_by_columns),
        aggregate_functions=frozenset(aggregate_functions),
        cte_names=frozenset(cte_names),
    )


def _top_overlap_terms(left: Iterable[str], right: Iterable[str], *, limit: int = 4) -> list[str]:
    return sorted(set(left) & set(right))[:limit]


def _confidence_band(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.70:
        return "medium"
    return "low"


def _collect_similarity_profiles(context: RuleContext) -> list[ModelSimilarityProfile]:
    profiles: list[ModelSimilarityProfile] = []
    for model in context.manifest_data.models.values():
        if context.governance_config.is_path_excluded(model.file_path):
            continue
        sql = model.raw_code or context.sql_files.get(model.file_path, "")
        if not sql:
            continue
        profile = _parse_similarity_profile(model.name, model.file_path, model.layer, sql)
        if profile is not None:
            profiles.append(profile)
    return profiles


def _build_similarity_edges(
    profiles: list[ModelSimilarityProfile],
    *,
    min_score: float,
) -> list[SimilarityEdge]:
    candidate_edges: list[SimilarityEdge] = []
    for left, right in combinations(profiles, 2):
        if left.layer != right.layer:
            continue
        if left.file_path == right.file_path:
            continue

        input_score = _jaccard(left.inputs, right.inputs)
        selected_score = _jaccard(left.selected_columns, right.selected_columns)
        join_score = _jaccard(left.join_targets, right.join_targets)
        filter_score = _jaccard(left.filter_columns, right.filter_columns)
        group_score = _jaccard(left.group_by_columns, right.group_by_columns)
        agg_score = _jaccard(left.aggregate_functions, right.aggregate_functions)
        cte_score = _jaccard(left.cte_names, right.cte_names)

        weighted_score = (
            input_score * 0.28
            + selected_score * 0.24
            + join_score * 0.14
            + filter_score * 0.10
            + group_score * 0.08
            + agg_score * 0.08
            + cte_score * 0.08
        )

        # Require at least some shared lineage or selected shape to avoid noisy pairs.
        if weighted_score < min_score:
            continue
        if input_score < 0.34 and selected_score < 0.50:
            continue

        candidate_edges.append(
            SimilarityEdge(
                left=left,
                right=right,
                score=weighted_score,
                input_score=input_score,
                selected_score=selected_score,
                join_score=join_score,
                filter_score=filter_score,
                group_score=group_score,
                agg_score=agg_score,
                cte_score=cte_score,
            )
        )

    candidate_edges.sort(key=lambda item: item.score, reverse=True)
    return candidate_edges


def _shared_model_name(model_names: list[str], shared_inputs: list[str]) -> str:
    if shared_inputs:
        clean: list[str] = []
        for inp in sorted(shared_inputs)[:2]:
            if inp.startswith("ref_"):
                clean.append(inp[4:])  # strip "ref_" → "stg_orders"
            elif inp.startswith("source_"):
                # "source_ecommerce_raw_orders" → keep only the table part
                parts = inp.split("_", 2)
                clean.append(parts[2] if len(parts) > 2 else inp)
            else:
                clean.append(inp)
        return f"int_{'_'.join(clean)}_shared"

    cleaned = []
    for name in model_names[:2]:
        cleaned_name = re.sub(r"^(stg|int|fct|dim)_", "", name)
        cleaned_name = cleaned_name.replace("__", "_")
        cleaned.append(cleaned_name)
    return f"int_{'_'.join(cleaned)}_shared"


def _majority_overlap(
    profiles: list[ModelSimilarityProfile],
    extractor: callable,
    *,
    min_count: int,
    limit: int = 6,
) -> list[str]:
    counts: Counter[str] = Counter()
    for profile in profiles:
        counts.update(extractor(profile))
    return [
        term
        for term, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= min_count
    ][:limit]


def _cluster_anchor(
    profiles: list[ModelSimilarityProfile],
    edges: list[SimilarityEdge],
    changed_files: list[str] | None,
) -> ModelSimilarityProfile:
    edge_counts: Counter[str] = Counter()
    for edge in edges:
        edge_counts[edge.left.file_path] += 1
        edge_counts[edge.right.file_path] += 1

    ordered = sorted(profiles, key=lambda profile: (-edge_counts[profile.file_path], profile.model_name))
    changed = set(changed_files or [])
    for profile in ordered:
        if profile.file_path in changed:
            return profile
    return ordered[0]


def _pair_feature_details(
    left: ModelSimilarityProfile,
    right: ModelSimilarityProfile,
) -> tuple[list[str], list[str], list[str], list[str]]:
    return (
        _top_overlap_terms(left.inputs, right.inputs),
        _top_overlap_terms(left.selected_columns, right.selected_columns),
        sorted(left.aggregate_functions & right.aggregate_functions),
        sorted(left.filter_columns & right.filter_columns),
    )


def _pair_rule_min_score(config, default: float) -> float:
    rule = config.reuse.rules.get("model_similarity_candidates")
    if not rule:
        return default
    extra = rule.model_extra or {}
    return float(extra.get("min_score", default))


@register_rule
class ModelSimilarityCandidatesRule(BaseRule):
    rule_id = "reuse.model_similarity_candidates"
    category = "reuse"
    description = (
        "Models with highly similar SQL structure, inputs, and transformations are likely "
        "candidates for consolidation into a shared model"
    )
    default_severity = Severity.INFO

    _DEFAULT_MIN_SCORE = 0.72
    _DEFAULT_MAX_MATCHES_PER_MODEL = 3

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        min_score = float(
            self.get_rule_config_value(context.governance_config, "min_score", self._DEFAULT_MIN_SCORE)
        )
        max_matches_per_model = int(
            self.get_rule_config_value(
                context.governance_config,
                "max_matches_per_model",
                self._DEFAULT_MAX_MATCHES_PER_MODEL,
            )
        )

        profiles = _collect_similarity_profiles(context)
        candidate_pairs = _build_similarity_edges(profiles, min_score=min_score)

        matches_by_model: dict[str, int] = defaultdict(int)
        violations: list[Violation] = []
        for edge in candidate_pairs:
            score = edge.score
            left = edge.left
            right = edge.right
            if matches_by_model[left.model_name] >= max_matches_per_model:
                continue
            if matches_by_model[right.model_name] >= max_matches_per_model:
                continue

            anchor = left
            other = right
            if context.changed_files:
                changed = set(context.changed_files)
                if right.file_path in changed and left.file_path not in changed:
                    anchor = right
                    other = left

            shared_inputs, shared_columns, shared_aggregates, shared_filters = _pair_feature_details(anchor, other)
            shared_features = []
            if shared_inputs:
                shared_features.append(f"shared inputs: {', '.join(shared_inputs)}")
            if shared_columns:
                shared_features.append(f"shared selected columns: {', '.join(shared_columns)}")
            if shared_aggregates:
                shared_features.append("shared aggregates: " + ", ".join(shared_aggregates))

            feature_summary = "; ".join(shared_features) if shared_features else "shared SQL structure"
            suggested_name = _shared_model_name([anchor.model_name, other.model_name], shared_inputs)
            confidence = _confidence_band(score)

            violations.append(
                Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=anchor.model_name,
                    file_path=anchor.file_path,
                    message=(
                        f"Model '{anchor.model_name}' is highly similar to '{other.model_name}' "
                        f"(similarity score: {score:.2f}, confidence: {confidence}). "
                        f"Both models share {feature_summary}, which suggests duplicated transformation logic."
                    ),
                    suggestion=(
                        f"Review '{anchor.model_name}' and '{other.model_name}' as consolidation candidates. "
                        f"Consider extracting their shared logic into a reusable intermediate model such as "
                        f"'{suggested_name}.sql', then ref() that model from both downstream consumers."
                    ),
                    details={
                        "recommendation_type": "pair",
                        "similarity_score": round(score, 3),
                        "confidence_band": confidence,
                        "paired_model_name": other.model_name,
                        "paired_file_path": other.file_path,
                        "shared_inputs": shared_inputs,
                        "shared_selected_columns": shared_columns,
                        "shared_aggregates": shared_aggregates,
                        "shared_filters": shared_filters,
                        "suggested_shared_model": f"{suggested_name}.sql",
                    },
                )
            )
            matches_by_model[left.model_name] += 1
            matches_by_model[right.model_name] += 1

        return violations


@register_rule
class ModelSimilarityClustersRule(BaseRule):
    rule_id = "reuse.model_similarity_clusters"
    category = "reuse"
    description = (
        "Groups of highly similar models form a reuse cluster and should converge on a shared "
        "intermediate model instead of maintaining several near-duplicate branches"
    )
    default_severity = Severity.INFO

    _DEFAULT_MIN_CLUSTER_SIZE = 3
    _DEFAULT_MIN_SCORE = 0.72

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        min_cluster_size = int(
            self.get_rule_config_value(
                context.governance_config,
                "min_cluster_size",
                self._DEFAULT_MIN_CLUSTER_SIZE,
            )
        )
        min_score = _pair_rule_min_score(context.governance_config, self._DEFAULT_MIN_SCORE)

        profiles = _collect_similarity_profiles(context)
        candidate_edges = _build_similarity_edges(profiles, min_score=min_score)
        if not candidate_edges:
            return []

        profile_by_path = {profile.file_path: profile for profile in profiles}
        adjacency: dict[str, set[str]] = defaultdict(set)
        edge_lookup: dict[frozenset[str], SimilarityEdge] = {}
        for edge in candidate_edges:
            adjacency[edge.left.file_path].add(edge.right.file_path)
            adjacency[edge.right.file_path].add(edge.left.file_path)
            edge_lookup[frozenset({edge.left.file_path, edge.right.file_path})] = edge

        visited: set[str] = set()
        violations: list[Violation] = []

        for start in sorted(adjacency):
            if start in visited:
                continue

            stack = [start]
            component_paths: set[str] = set()
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                component_paths.add(current)
                stack.extend(adjacency[current] - visited)

            if len(component_paths) < min_cluster_size:
                continue

            component_profiles = sorted(
                [profile_by_path[path] for path in component_paths],
                key=lambda profile: profile.model_name,
            )
            component_edges = [
                edge
                for edge in candidate_edges
                if edge.left.file_path in component_paths and edge.right.file_path in component_paths
            ]
            if not component_edges:
                continue

            cluster_average = sum(edge.score for edge in component_edges) / len(component_edges)
            cluster_peak = max(edge.score for edge in component_edges)
            confidence = _confidence_band(cluster_average)
            overlap_threshold = max(2, ceil(len(component_profiles) / 2))

            shared_inputs = _majority_overlap(
                component_profiles, lambda profile: profile.inputs, min_count=overlap_threshold
            )
            shared_columns = _majority_overlap(
                component_profiles,
                lambda profile: profile.selected_columns,
                min_count=overlap_threshold,
            )
            shared_aggregates = _majority_overlap(
                component_profiles,
                lambda profile: profile.aggregate_functions,
                min_count=overlap_threshold,
            )
            shared_filters = _majority_overlap(
                component_profiles,
                lambda profile: profile.filter_columns,
                min_count=overlap_threshold,
            )

            shared_features = []
            if shared_inputs:
                shared_features.append(f"shared inputs: {', '.join(shared_inputs)}")
            if shared_columns:
                shared_features.append(f"shared selected columns: {', '.join(shared_columns)}")
            if shared_aggregates:
                shared_features.append(f"shared aggregates: {', '.join(shared_aggregates)}")
            if shared_filters:
                shared_features.append(f"shared filters: {', '.join(shared_filters)}")
            feature_summary = "; ".join(shared_features) if shared_features else "strongly overlapping SQL structure"

            model_names = [profile.model_name for profile in component_profiles]
            anchor = _cluster_anchor(component_profiles, component_edges, context.changed_files)
            suggested_name = _shared_model_name(model_names, shared_inputs)
            cluster_label = ", ".join(model_names[:4])
            if len(model_names) > 4:
                cluster_label = f"{cluster_label}, and {len(model_names) - 4} more"

            example_pairs = [
                {
                    "left_model_name": edge.left.model_name,
                    "right_model_name": edge.right.model_name,
                    "similarity_score": round(edge.score, 3),
                }
                for edge in component_edges[:3]
            ]

            violations.append(
                Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=anchor.model_name,
                    file_path=anchor.file_path,
                    message=(
                        f"Models {cluster_label} form a reuse cluster ({len(model_names)} models, "
                        f"average similarity: {cluster_average:.2f}, peak: {cluster_peak:.2f}, "
                        f"confidence: {confidence}). They share {feature_summary}, which suggests "
                        "they should converge on one shared intermediate model."
                    ),
                    suggestion=(
                        f"Create a reusable intermediate such as '{suggested_name}.sql' for the common logic, "
                        f"then have cluster members {', '.join(model_names)} ref() it and keep only "
                        "their genuinely divergent downstream logic."
                    ),
                    details={
                        "recommendation_type": "cluster",
                        "confidence_band": confidence,
                        "cluster_models": model_names,
                        "cluster_size": len(model_names),
                        "cluster_average_score": round(cluster_average, 3),
                        "cluster_peak_score": round(cluster_peak, 3),
                        "shared_inputs": shared_inputs,
                        "shared_selected_columns": shared_columns,
                        "shared_aggregates": shared_aggregates,
                        "shared_filters": shared_filters,
                        "suggested_shared_model": f"{suggested_name}.sql",
                        "cluster_example_pairs": example_pairs,
                    },
                )
            )

        return violations


@register_rule
class DuplicateSourceStagingRule(BaseRule):
    rule_id = "reuse.duplicate_source_staging"
    category = "reuse"
    description = (
        "Multiple staging models reference the same source table — "
        "each should have exactly one staging model; downstream models should ref() that one"
    )
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        # Map source_id -> list of staging models that depend on it
        source_to_staging: dict[str, list[str]] = defaultdict(list)

        for model in context.manifest_data.models.values():
            if model.layer != "staging":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            for src_id in model.depends_on_sources:
                source_to_staging[src_id].append(model.unique_id)

        for src_id, staging_ids in source_to_staging.items():
            if len(staging_ids) < 2:
                continue

            src = context.manifest_data.sources.get(src_id)
            src_label = f"{src.source_name}.{src.name}" if src else src_id

            staging_names = []
            for mid in staging_ids:
                m = context.manifest_data.models.get(mid)
                staging_names.append(m.name if m else mid)

            for mid in staging_ids:
                model = context.manifest_data.models.get(mid)
                if not model:
                    continue
                others = [n for n in staging_names if n != model.name]
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=(
                        f"Source '{src_label}' is staged by multiple models: "
                        f"{', '.join(staging_names)}. "
                        "Each source table should have exactly one staging model."
                    ),
                    suggestion=(
                        f"Consolidate into a single staging model (e.g., keep '{staging_names[0]}'). "
                        f"Models {', '.join(others)} should ref() that staging model instead of "
                        "staging the same source independently. "
                        "This prevents divergent transformations on the same raw data."
                    ),
                ))
        return violations


@register_rule
class SharedCTECandidatesRule(BaseRule):
    rule_id = "reuse.shared_cte_candidates"
    category = "reuse"
    description = (
        "The same CTE name appears across many models, suggesting duplicated logic "
        "that should be extracted into a shared intermediate model"
    )
    default_severity = Severity.INFO

    # Minimum number of models that must share a CTE name to flag it
    _DEFAULT_MIN_OCCURRENCES = 3

    _DEFAULT_MIN_SQL_LENGTH = 48

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        min_occurrences = self.get_rule_config_value(
            context.governance_config, "min_occurrences", self._DEFAULT_MIN_OCCURRENCES
        )
        min_sql_length = int(
            self.get_rule_config_value(
                context.governance_config,
                "min_sql_length",
                self._DEFAULT_MIN_SQL_LENGTH,
            )
        )
        violations = []

        # Map normalized CTE body -> list of (model_name, file_path, cte_name)
        cte_occurrences: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code or context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            try:
                parsed = sqlglot.parse_one(_sanitize_sql_for_similarity(sql), read="duckdb")
            except sqlglot.errors.ParseError:
                continue

            found_in_model: set[str] = set()
            for cte in parsed.find_all(exp.CTE):
                cte_name = cte.alias_or_name.lower()
                body = cte.this
                body_select = _root_select(body)
                if body_select is not None and _is_trivial_passthrough_select(body_select):
                    continue

                fingerprint = _normalized_expression_sql(body, strip_qualifiers=True)
                if len(fingerprint) < min_sql_length or fingerprint in found_in_model:
                    continue
                cte_occurrences[fingerprint].append((model.name, model.file_path, cte_name))
                found_in_model.add(fingerprint)

        for fingerprint, occurrences in cte_occurrences.items():
            if len(occurrences) < min_occurrences:
                continue

            model_names = [occurrence[0] for occurrence in occurrences]
            cte_names = sorted({occurrence[2] for occurrence in occurrences})
            suggested_name = _shared_model_name(model_names, [])

            for model_name, file_path, cte_name in occurrences:
                others = [name for name in model_names if name != model_name]
                violations.append(
                    Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model_name,
                        file_path=file_path,
                        message=(
                            f"Equivalent CTE logic appears in {len(occurrences)} models "
                            f"under names such as {', '.join(cte_names[:4])}. "
                            f"Models {', '.join(model_names[:5])}{'...' if len(model_names) > 5 else ''} "
                            "are repeating the same intermediate transformation."
                        ),
                        suggestion=(
                            f"Extract the shared CTE logic currently named '{cte_name}' into a dedicated "
                            f"intermediate model such as '{suggested_name}.sql', then have "
                            f"{', '.join(others[:4])}{' and others' if len(others) > 4 else ''} ref() it."
                        ),
                        details={
                            "matching_models": model_names,
                            "matching_cte_names": cte_names,
                            "cte_fingerprint": fingerprint,
                            "suggested_shared_model": f"{suggested_name}.sql",
                        },
                    )
                )
        return violations


@register_rule
class MultipleModelsFromSameSourceRule(BaseRule):
    rule_id = "reuse.multiple_models_from_same_source"
    category = "reuse"
    description = (
        "Multiple non-staging models reference the same source table directly — "
        "they should all go through a single shared staging model"
    )
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        # Map source_id -> list of non-staging models that depend on it directly
        source_to_models: dict[str, list[str]] = defaultdict(list)

        for model in context.manifest_data.models.values():
            if model.layer == "staging":
                continue
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            for src_id in model.depends_on_sources:
                source_to_models[src_id].append(model.unique_id)

        for src_id, model_ids in source_to_models.items():
            if len(model_ids) < 2:
                continue

            src = context.manifest_data.sources.get(src_id)
            src_label = f"{src.source_name}.{src.name}" if src else src_id

            model_names = []
            for mid in model_ids:
                m = context.manifest_data.models.get(mid)
                model_names.append(m.name if m else mid)

            for mid in model_ids:
                model = context.manifest_data.models.get(mid)
                if not model:
                    continue
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=(
                        f"Source '{src_label}' is referenced directly by {len(model_ids)} "
                        f"non-staging models: {', '.join(model_names)}. "
                        "Each source should be staged once and shared via ref()."
                    ),
                    suggestion=(
                        f"Create a single staging model for source '{src_label}' "
                        "(e.g., stg_<source>__<table>.sql) and update all "
                        f"{len(model_ids)} models to ref() it. "
                        "This centralizes source field mapping and ensures type casting "
                        "is done consistently in one place."
                    ),
                ))
        return violations


@register_rule
class IdenticalSelectColumnsRule(BaseRule):
    rule_id = "reuse.identical_select_columns"
    category = "reuse"
    description = (
        "Multiple models select the exact same set of columns from the same base — "
        "strong signal of copy-paste duplication that should be a shared model"
    )
    default_severity = Severity.INFO

    _MIN_COLUMNS = 5  # Only flag when there are enough columns to be meaningful

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        # Map (external_inputs, selected_columns, layer) -> list of (model_name, file_path)
        column_groups: dict[tuple, list[tuple[str, str]]] = defaultdict(list)

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code or context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            profile = _parse_similarity_profile(model.name, model.file_path, model.layer, sql)
            if profile is None or len(profile.selected_columns) < self._MIN_COLUMNS or not profile.inputs:
                continue

            key = (profile.inputs, profile.selected_columns, profile.layer)
            column_groups[key].append((model.name, model.file_path))

        for (inputs, cols, _layer), models in column_groups.items():
            if len(models) < 2:
                continue

            model_names = [m[0] for m in models]
            input_label = ", ".join(sorted(inputs)[:3])
            for model_name, file_path in models:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model_name,
                    file_path=file_path,
                    message=(
                        f"Model '{model_name}' selects the same {len(cols)} columns from "
                        f"'{input_label}' as: {', '.join(n for n in model_names if n != model_name)}. "
                        "This is likely duplicated logic."
                    ),
                    suggestion=(
                        f"Extract the shared column selection from '{input_label}' into a "
                        "single intermediate model and ref() it from all consumers. "
                        "This ensures column aliasing and type casting are done once."
                    ),
                    details={
                        "shared_inputs": sorted(inputs),
                        "shared_selected_columns": sorted(cols),
                    },
                ))
        return violations


@register_rule
class DuplicateColumnDerivationsRule(BaseRule):
    rule_id = "reuse.duplicate_column_derivations"
    category = "reuse"
    description = (
        "The same non-trivial derived column expression appears in multiple models, "
        "suggesting business logic should be centralized"
    )
    default_severity = Severity.INFO

    _DEFAULT_MIN_OCCURRENCES = 3

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        min_occurrences = int(
            self.get_rule_config_value(
                context.governance_config,
                "min_occurrences",
                self._DEFAULT_MIN_OCCURRENCES,
            )
        )
        derivations: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)
        violations: list[Violation] = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            sql = model.raw_code or context.sql_files.get(model.file_path, "")
            if not sql:
                continue

            try:
                parsed = sqlglot.parse_one(_sanitize_sql_for_similarity(sql), read="duckdb")
            except sqlglot.errors.ParseError:
                continue

            select = _root_select(parsed)
            if select is None:
                continue

            seen_in_model: set[tuple[str, str, str]] = set()
            for projection in select.expressions:
                alias = _normalized_select_name(projection)
                expression = _projection_expression(projection)
                if not alias or isinstance(expression, (exp.Column, exp.Literal)):
                    continue

                fingerprint = _normalized_expression_sql(expression, strip_qualifiers=True)
                key = (model.layer, alias, fingerprint)
                if key in seen_in_model:
                    continue
                derivations[key].append((model.name, model.file_path))
                seen_in_model.add(key)

        for (layer, alias, fingerprint), occurrences in derivations.items():
            if len(occurrences) < min_occurrences:
                continue

            model_names = [model_name for model_name, _ in occurrences]
            suggested_name = f"int_{alias}_shared.sql"
            for model_name, file_path in occurrences:
                others = [name for name in model_names if name != model_name]
                violations.append(
                    Violation(
                        rule_id=self.rule_id,
                        severity=severity,
                        model_name=model_name,
                        file_path=file_path,
                        message=(
                            f"Derived column '{alias}' uses the same logic in {len(occurrences)} "
                            f"{layer} models: {', '.join(model_names[:5])}{'...' if len(model_names) > 5 else ''}. "
                            "This is a strong signal of duplicated business logic."
                        ),
                        suggestion=(
                            f"Centralize the '{alias}' derivation in a shared upstream model or macro. "
                            f"A good starting point is '{suggested_name}', then keep only truly distinct "
                            f"downstream logic in {', '.join(others[:4])}{' and others' if len(others) > 4 else ''}."
                        ),
                        details={
                            "derived_column_alias": alias,
                            "derived_expression": fingerprint,
                            "matching_models": model_names,
                            "suggested_shared_model": suggested_name,
                        },
                    )
                )

        return violations
